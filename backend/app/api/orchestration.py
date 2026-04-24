import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory, get_db
from app.dependencies.auth import get_current_user
from app.engine.orchestrator import orchestrator
from app.models import Todo, SchedulePlan, ScheduleTask, Agent, WAgent, Orchestration, User
from app.services.schedule_rebalance import rebalance_schedule_tasks
from app.services.sse_manager import sse_manager
from app.utils.timezone import (
    beijing_to_utc_naive,
    parse_datetime_value,
    utc_now_naive,
    utc_to_beijing_iso_from_any,
)
from app.utils.recurrence import normalize_cron_expression, validate_cron_expression
from loguru import logger

_background_tasks: set[asyncio.Task] = set()

router = APIRouter(prefix="/orchestration", tags=["orchestration"])

_RESPONSE_TIME_KEYS = {
    "submitted_at",
    "deadline",
    "created_at",
    "updated_at",
    "start_time",
    "completed_at",
    "scheduled_at",
    "original_scheduled_at",
    "current_scheduled_at",
    "next_run_at",
}


def _convert_times_to_beijing(data):
    if isinstance(data, list):
        return [_convert_times_to_beijing(item) for item in data]
    if isinstance(data, dict):
        converted = {}
        for key, value in data.items():
            if key in _RESPONSE_TIME_KEYS:
                converted[key] = utc_to_beijing_iso_from_any(value)
            else:
                converted[key] = _convert_times_to_beijing(value)
        return converted
    return data


async def _broadcast_orchestration_complete(
    orch_id: str, status: str, error: str | None = None, removed: bool = False
) -> None:
    await sse_manager.broadcast(
        "orchestration_complete",
        {"orch_id": orch_id, "status": status, "error": error, "removed": removed},
    )


class SubmitPayload(BaseModel):
    todo_ids: list[str]


def _can_access_todo(current_user: User, todo: Todo) -> bool:
    if getattr(current_user, "is_superuser", False):
        return True
    return todo.creator_id == current_user.id


def _can_access_orchestration(current_user: User, orch: Orchestration) -> bool:
    if getattr(current_user, "is_superuser", False):
        return True
    return orch.user_id == current_user.id


# ---------------------------------------------------------------------------
# Public helpers – imported by scheduling.py, todos.py, scheduler.py
# ---------------------------------------------------------------------------


async def get_orchestration(db: AsyncSession, orch_id: str) -> Orchestration | None:
    """Return the ORM object (for callers that need to mutate it)."""
    return await db.get(Orchestration, orch_id)


async def get_orchestration_entry(db: AsyncSession, orch_id: str) -> dict | None:
    """Return a plain dict snapshot (read-only convenience)."""
    orch = await db.get(Orchestration, orch_id)
    return orch.to_dict() if orch else None


async def update_orchestration_status(
    db: AsyncSession, orch_id: str, status: str, error: str | None = None
) -> bool:
    orch = await db.get(Orchestration, orch_id)
    if not orch:
        return False
    orch.status = status
    if error:
        orch.error = error
    if status == "pending_confirm":
        _restore_plan_input_params_from_snapshot(orch)
    await db.flush()
    return True


def map_orchestration_status_to_todo_status(status: str | None) -> str:
    if status in {"analyzing", "pending_confirm", "failed"}:
        return "orchestrating"
    if status == "confirmed":
        return "scheduling"
    if status == "completed":
        return "completed"
    return "pending_confirm"


def build_orchestration_summary(todo_items, fallback: str = "未命名任务") -> str:
    items = list(todo_items or [])
    if not items:
        return fallback

    def _get_text(item) -> str:
        if isinstance(item, dict):
            return (item.get("title") or "").strip()
        return (getattr(item, "title", None) or "").strip()

    first_text = next((_get_text(item) for item in items if _get_text(item)), "")
    if not first_text:
        return fallback
    if len(items) > 1:
        return f"{first_text} 等 {len(items)} 个任务"
    return first_text


async def sync_todos_for_orchestration(
    db: AsyncSession, orch_id: str, status_override: str | None = None
) -> None:
    orch = await db.get(Orchestration, orch_id)
    orchestration_status = status_override or (orch.status if orch else None)
    if not orchestration_status:
        return

    snapshot_ids = [
        item.get("id")
        for item in ((orch.todos_snapshot if orch else None) or [])
        if item.get("id")
    ]
    if snapshot_ids:
        result = await db.execute(select(Todo).where(Todo.id.in_(snapshot_ids)))
    else:
        result = await db.execute(
            select(Todo).where(Todo.orchestration_id == orch_id)
        )
    todos = result.scalars().all()
    if not todos:
        return

    todo_status = map_orchestration_status_to_todo_status(orchestration_status)
    should_clear_orchestration_id = orchestration_status == "cancelled"
    completed_at: datetime | None = None
    if todo_status == "completed":
        schedule_task_result = await db.execute(
            select(ScheduleTask).where(
                ScheduleTask.orchestration_id == orch_id,
                ScheduleTask.completed_at.is_not(None),
            )
        )
        for task in schedule_task_result.scalars().all():
            if task.completed_at is None:
                continue
            if completed_at is None or task.completed_at > completed_at:
                completed_at = task.completed_at
        if completed_at is None:
            completed_at = utc_now_naive()

    for todo in todos:
        todo.status = todo_status
        todo.orchestration_id = None if should_clear_orchestration_id else orch_id
        todo.completed_at = completed_at if todo_status == "completed" else None

    await db.flush()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_plan_time_value(
    value: str | datetime | None, assume_beijing: bool = True
) -> str | None:
    if not value:
        return None
    parsed = parse_datetime_value(value)
    if parsed is None:
        return str(value)
    if parsed.tzinfo is not None:
        normalized = parsed.astimezone(UTC).replace(tzinfo=None, microsecond=0)
    elif assume_beijing:
        normalized = beijing_to_utc_naive(parsed)
    else:
        normalized = parsed.replace(microsecond=0)
    return normalized.isoformat()


def _parse_schedule_datetime(value: str | None) -> datetime:
    normalized = _normalize_plan_time_value(value, assume_beijing=False)
    if not normalized:
        return utc_now_naive()
    try:
        return datetime.fromisoformat(normalized).replace(microsecond=0)
    except ValueError:
        return utc_now_naive()


def _normalize_recurrence_payload(data: dict | None) -> dict:
    payload = data or {}
    is_recurring = bool(payload.get("is_recurring", False))
    if not is_recurring:
        return {
            "is_recurring": False,
            "recurrence_cron": None,
            "recurrence_count": 0,
        }

    recurrence_cron = normalize_cron_expression(payload.get("recurrence_cron"))
    if not recurrence_cron or not validate_cron_expression(recurrence_cron):
        raise HTTPException(status_code=400, detail="循环表达式无效，请输入合法 cron")
    recurrence_count = max(0, int(payload.get("recurrence_count") or 0))
    return {
        "is_recurring": True,
        "recurrence_cron": recurrence_cron,
        "recurrence_count": recurrence_count,
    }


def _build_recurrence_defaults_from_todos(todos: list[Todo]) -> dict:
    if not todos:
        return _normalize_recurrence_payload(None)
    first = todos[0]
    return _normalize_recurrence_payload(
        {
            "is_recurring": getattr(first, "is_recurring", False),
            "recurrence_cron": getattr(first, "recurrence_cron", None),
            "recurrence_count": getattr(first, "recurrence_count", 0),
        }
    )


def _apply_recurrence_to_plan(plan: dict | None, defaults: dict) -> dict:
    merged = dict(plan or {})
    recurrence = _normalize_recurrence_payload(
        {
            "is_recurring": merged.get(
                "is_recurring", defaults.get("is_recurring", False)
            ),
            "recurrence_cron": merged.get(
                "recurrence_cron", defaults.get("recurrence_cron")
            ),
            "recurrence_count": merged.get(
                "recurrence_count", defaults.get("recurrence_count", 0)
            ),
        }
    )
    merged.update(recurrence)
    return merged


async def _sync_todo_recurrence_for_orchestration(
    db: AsyncSession, orch: Orchestration
) -> str | None:
    todo_ids = [
        item.get("id") for item in (orch.todos_snapshot or []) if item.get("id")
    ]
    if not todo_ids:
        return None
    normalized = _normalize_recurrence_payload(orch.plan or {})
    result = await db.execute(select(Todo).where(Todo.id.in_(todo_ids)))
    todos = result.scalars().all()

    mismatch = False
    for todo in todos:
        if bool(todo.is_recurring) != normalized["is_recurring"]:
            mismatch = True
        if (todo.recurrence_cron or None) != normalized["recurrence_cron"]:
            mismatch = True

    for todo in todos:
        todo.is_recurring = normalized["is_recurring"]
        todo.recurrence_cron = normalized["recurrence_cron"]
        todo.recurrence_count = normalized["recurrence_count"]
    await db.flush()

    if mismatch:
        return "检测到待办任务中的循环设置与编排设置不一致，已同步更新待办任务循环设置。"
    return None


async def _cancel_schedule_for_orchestration(
    db: AsyncSession, orch_id: str
) -> None:
    existing_task_result = await db.execute(
        select(ScheduleTask).where(ScheduleTask.orchestration_id == orch_id)
    )
    schedule_tasks = existing_task_result.scalars().all()
    if not schedule_tasks:
        return

    plan_ids = {task.plan_id for task in schedule_tasks if task.plan_id}
    now = utc_now_naive()

    for task in schedule_tasks:
        task.status = "cancelled"
        task.error_message = task.error_message or "编排已取消"
        if task.completed_at is None:
            task.completed_at = now

    if plan_ids:
        plans_result = await db.execute(
            select(SchedulePlan).where(SchedulePlan.id.in_(plan_ids))
        )
        for plan in plans_result.scalars().all():
            plan.status = "cancelled"

    await db.flush()


async def ensure_schedule_for_orchestration(
    db: AsyncSession, orch_id: str, orch: Orchestration
) -> None:
    plan_data = orch.plan or {}
    recurrence = _normalize_recurrence_payload(plan_data)

    parent_task_result = await db.execute(
        select(ScheduleTask)
        .where(
            ScheduleTask.orchestration_id == orch_id,
            ScheduleTask.is_parent.is_(True),
            ScheduleTask.status != "cancelled",
        )
        .order_by(ScheduleTask.created_at.desc())
    )
    parent_task = parent_task_result.scalars().first()

    schedule_plan = None
    if parent_task:
        schedule_plan = await db.get(SchedulePlan, parent_task.plan_id)
        if schedule_plan and schedule_plan.status == "cancelled":
            parent_task = None
            schedule_plan = None

    if schedule_plan is None:
        schedule_plan = SchedulePlan(
            name=orch.summary or f"编排任务 {orch_id}",
            status="active",
            is_recurring=False,
        )
        db.add(schedule_plan)
        await db.flush()

    recommended_id = plan_data.get("recommended_id")
    plan_type = plan_data.get("plan_type")
    agent_id = recommended_id if plan_type == "agent" and recommended_id else None
    wagent_id = (
        recommended_id
        if plan_type in ("wagent", "new_wagent") and recommended_id
        else None
    )
    scheduled_at = _parse_schedule_datetime(plan_data.get("start_time"))
    recurrence_limit = recurrence["recurrence_count"] if recurrence["is_recurring"] else 1

    # recurring orchestration -> parent task container
    if recurrence["is_recurring"]:
        if parent_task is None:
            parent_task = ScheduleTask(
                plan_id=schedule_plan.id,
                parent_task_id=None,
                is_parent=True,
                orchestration_id=orch_id,
                agent_id=agent_id,
                wagent_id=wagent_id,
                status="recurring",
                priority=plan_data.get("priority") or "medium",
                scheduled_at=scheduled_at,
                original_scheduled_at=scheduled_at,
                current_scheduled_at=scheduled_at,
                delay_count=0,
                input_params=plan_data.get("input_params") or {},
                recurrence_cron=recurrence["recurrence_cron"],
                recurrence_limit=recurrence_limit,
                recurrence_done=0,
            )
            db.add(parent_task)
        else:
            parent_task.plan_id = schedule_plan.id
            parent_task.parent_task_id = None
            parent_task.is_parent = True
            parent_task.agent_id = agent_id
            parent_task.wagent_id = wagent_id
            parent_task.status = "recurring"
            parent_task.priority = (
                plan_data.get("priority") or parent_task.priority or "medium"
            )
            parent_task.scheduled_at = scheduled_at
            if parent_task.original_scheduled_at is None:
                parent_task.original_scheduled_at = scheduled_at
            parent_task.current_scheduled_at = scheduled_at
            parent_task.delay_count = 0
            parent_task.input_params = plan_data.get("input_params") or {}
            parent_task.error_message = None
            parent_task.recurrence_cron = recurrence["recurrence_cron"]
            parent_task.recurrence_limit = recurrence_limit
    else:
        # non-recurring orchestration -> direct executable task (not parent)
        if parent_task is None:
            parent_task = ScheduleTask(
                plan_id=schedule_plan.id,
                parent_task_id=None,
                is_parent=False,
                orchestration_id=orch_id,
                agent_id=agent_id,
                wagent_id=wagent_id,
                status="pending",
                priority=plan_data.get("priority") or "medium",
                scheduled_at=scheduled_at,
                original_scheduled_at=scheduled_at,
                current_scheduled_at=scheduled_at,
                delay_count=0,
                input_params=plan_data.get("input_params") or {},
                recurrence_cron=None,
                recurrence_limit=1,
                recurrence_done=0,
            )
            db.add(parent_task)
        else:
            parent_task.plan_id = schedule_plan.id
            parent_task.parent_task_id = None
            parent_task.is_parent = False
            parent_task.agent_id = agent_id
            parent_task.wagent_id = wagent_id
            parent_task.status = "pending"
            parent_task.priority = (
                plan_data.get("priority") or parent_task.priority or "medium"
            )
            parent_task.scheduled_at = scheduled_at
            if parent_task.original_scheduled_at is None:
                parent_task.original_scheduled_at = scheduled_at
            parent_task.current_scheduled_at = scheduled_at
            parent_task.delay_count = 0
            parent_task.input_params = plan_data.get("input_params") or {}
            parent_task.error_message = None
            parent_task.recurrence_cron = None
            parent_task.recurrence_limit = 1
            parent_task.recurrence_done = 0

    schedule_plan.name = orch.summary or schedule_plan.name
    schedule_plan.status = "active"
    schedule_plan.is_recurring = recurrence["is_recurring"]
    schedule_plan.recurrence_cron = recurrence["recurrence_cron"]
    schedule_plan.recurrence_count = recurrence["recurrence_count"]

    if not recurrence["is_recurring"]:
        parent_task.recurrence_done = 0

    await db.flush()


def _build_recommended_target(
    target_type: str, target_id: str | None, target_name: str | None
) -> dict | None:
    if not target_id:
        return None
    return {
        "id": target_id,
        "name": target_name or "",
        "is_enabled": True,
        "type": target_type,
    }


def _snapshot_llm_recommendation(orch: Orchestration) -> None:
    if orch.llm_recommended_id and orch.llm_recommended_type:
        return

    plan = orch.plan or {}
    suggested_agent = orch.suggested_agent
    suggested_wagent = orch.suggested_wagent
    plan_type = plan.get("plan_type")
    recommended_id = plan.get("recommended_id")
    recommended_name = plan.get("recommended_name")
    recommended_input_params = plan.get("input_params")

    def _snapshot_input_params_once() -> None:
        if orch.llm_recommended_input_params is not None:
            return
        orch.llm_recommended_input_params = (
            dict(recommended_input_params)
            if isinstance(recommended_input_params, dict)
            else {}
        )

    if suggested_agent and suggested_agent.get("id"):
        orch.llm_recommended_id = suggested_agent.get("id")
        orch.llm_recommended_name = (
            suggested_agent.get("name") or recommended_name or ""
        )
        orch.llm_recommended_type = "agent"
        _snapshot_input_params_once()
        return
    if suggested_wagent and suggested_wagent.get("id"):
        orch.llm_recommended_id = suggested_wagent.get("id")
        orch.llm_recommended_name = (
            suggested_wagent.get("name") or recommended_name or ""
        )
        orch.llm_recommended_type = "wagent"
        _snapshot_input_params_once()
        return
    if recommended_id and plan_type in {"agent", "wagent", "new_wagent"}:
        orch.llm_recommended_id = recommended_id
        orch.llm_recommended_name = recommended_name or ""
        orch.llm_recommended_type = (
            "wagent" if plan_type in {"wagent", "new_wagent"} else "agent"
        )
        _snapshot_input_params_once()


def _apply_selected_executor(
    orch: Orchestration,
    plan_type: str,
    recommended_id: str | None,
    recommended_name: str | None,
) -> None:
    plan = dict(orch.plan or {})
    plan["plan_type"] = plan_type
    plan["recommended_id"] = recommended_id or ""
    plan["recommended_name"] = recommended_name or ""
    orch.plan = plan
    orch.suggested_agent = (
        _build_recommended_target("agent", recommended_id, recommended_name)
        if plan_type == "agent"
        else None
    )
    orch.suggested_wagent = (
        _build_recommended_target("wagent", recommended_id, recommended_name)
        if plan_type in {"wagent", "new_wagent"}
        else None
    )


def _build_plan_input_params_for_selected_agent(raw_params) -> tuple[dict, list[str]]:
    editable_keys = orchestrator._extract_user_editable_keys(raw_params)
    if not editable_keys:
        return {}, []

    defaults = {key: "" for key in editable_keys}
    if isinstance(raw_params, list):
        for item in raw_params:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("key") or item.get("field")
            if not name or str(name) not in defaults:
                continue
            if item.get("default") is not None:
                defaults[str(name)] = item.get("default")
            elif item.get("value") is not None:
                defaults[str(name)] = item.get("value")
        return defaults, editable_keys

    if isinstance(raw_params, dict):
        for key in editable_keys:
            value = raw_params.get(key)
            if isinstance(value, dict):
                if value.get("default") is not None:
                    defaults[key] = value.get("default")
                elif value.get("value") is not None:
                    defaults[key] = value.get("value")
            elif value is not None:
                defaults[key] = value
        return defaults, editable_keys

    return defaults, editable_keys


def _restore_plan_input_params_from_snapshot(orch: Orchestration) -> None:
    plan = orch.plan
    if not plan:
        return
    current_params = plan.get("input_params")
    if current_params:
        return
    snapshot = orch.llm_recommended_input_params
    if not isinstance(snapshot, dict) or not snapshot:
        return
    rec_id = plan.get("recommended_id")
    llm_id = orch.llm_recommended_id
    should_restore = (rec_id and llm_id and rec_id == llm_id) or (
        not rec_id and not llm_id
    )
    if should_restore:
        plan = dict(plan)
        plan["input_params"] = dict(snapshot)
        orch.plan = plan


def _mark_analysis_error(orch: Orchestration, error: str) -> str:
    orch.status = "pending_confirm"
    orch.error = error
    return "pending_confirm"


def _build_llm_fallback_warning(plan_result: dict) -> str | None:
    llm_error = str(plan_result.get("llm_error") or "").strip()
    if not llm_error:
        return None
    return f"LLM 未返回有效结果，已自动使用兜底编排计划：{llm_error}"


# ---------------------------------------------------------------------------
# Background analysis task
# ---------------------------------------------------------------------------


def _apply_plan_to_orchestration(
    orch: Orchestration,
    plan_result: dict,
    recurrence_defaults: dict,
) -> str:
    """Apply a successful LLM plan result to the orchestration.
    Returns the event status string.
    """
    orch.status = plan_result.get("status", "pending_confirm")
    orch.plan = _apply_recurrence_to_plan(
        plan_result.get("plan"), recurrence_defaults
    )
    orch.llm_reason = plan_result.get("llm_reason")
    fallback_warning = _build_llm_fallback_warning(plan_result)
    orch.error = fallback_warning

    plan = orch.plan or {}
    if plan.get("plan_type") in ("agent",):
        rec_id = plan.get("recommended_id")
        rec_name = plan.get("recommended_name", "")
        orch.suggested_agent = (
            {"id": rec_id, "name": rec_name, "is_enabled": True, "type": "agent"}
            if rec_id
            else None
        )
    elif plan.get("plan_type") in ("wagent", "new_wagent"):
        rec_id = plan.get("recommended_id")
        rec_name = plan.get("recommended_name", "")
        orch.suggested_wagent = (
            {"id": rec_id, "name": rec_name, "is_enabled": True, "type": "wagent"}
            if rec_id
            else None
        )
    _snapshot_llm_recommendation(orch)
    return orch.status


async def _process_analysis(
    db: AsyncSession,
    orch_id: str,
    todo_ids: list[str],
    recurrence_defaults: dict,
) -> tuple[str, str | None]:
    """Core analysis logic – callable from tests with any DB session.

    Returns ``(event_status, error_msg)``.
    The caller is responsible for committing and broadcasting.
    """
    orch = await db.get(Orchestration, orch_id)
    if not orch or orch.status != "analyzing":
        return (orch.status if orch else "cancelled"), None

    event_status = "analyzing"
    error_msg: str | None = None

    try:
        plan_result = await orchestrator.orchestrate(db, todo_ids)

        if "error" in plan_result:
            event_status = _mark_analysis_error(orch, plan_result["error"])
            error_msg = plan_result["error"]
        else:
            event_status = _apply_plan_to_orchestration(
                orch, plan_result, recurrence_defaults
            )
            if orch.error:
                error_msg = orch.error
    except Exception as e:
        logger.error("Orchestration analysis failed for {}: {}", orch_id, e)
        event_status = _mark_analysis_error(orch, f"编排分析失败: {str(e)}")
        error_msg = str(e)

    if orch.status == "analyzing":
        event_status = _mark_analysis_error(
            orch, "LLM 分析超时或被中断，请重新编排"
        )
        error_msg = orch.error

    await sync_todos_for_orchestration(db, orch_id)
    return event_status, error_msg


async def _run_orchestration_analysis(
    orch_id: str,
    todo_ids: list[str],
    recurrence_defaults: dict,
) -> None:
    """Background task: run LLM analysis with its own DB session.

    Guarantees the orchestration status transitions out of "analyzing" before
    returning, regardless of whether the LLM call succeeds or fails.
    """
    event_status = "analyzing"
    error_msg: str | None = None

    try:
        async with async_session_factory() as db:
            event_status, error_msg = await _process_analysis(
                db, orch_id, todo_ids, recurrence_defaults
            )
            await db.commit()
    except Exception as e:
        logger.error(
            "Critical error in background orchestration for {}: {}", orch_id, e
        )
        try:
            async with async_session_factory() as recovery_db:
                orch = await recovery_db.get(Orchestration, orch_id)
                if orch and orch.status == "analyzing":
                    event_status = _mark_analysis_error(
                        orch, f"编排分析失败: {str(e)}"
                    )
                    error_msg = orch.error
                    await sync_todos_for_orchestration(recovery_db, orch_id)
                    await recovery_db.commit()
        except Exception:
            logger.error("Recovery commit also failed for {}", orch_id)

    try:
        await _broadcast_orchestration_complete(orch_id, event_status, error_msg)
    except Exception:
        pass


def _launch_analysis(
    orch_id: str,
    todo_ids: list[str],
    recurrence_defaults: dict,
) -> asyncio.Task:
    """Fire-and-forget the analysis background task."""
    task = asyncio.create_task(
        _run_orchestration_analysis(orch_id, todo_ids, recurrence_defaults)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def recover_stale_analyzing_orchestrations() -> int:
    """Reset orchestrations stuck at 'analyzing' (e.g. after server restart).

    Called during application startup.  Returns the number of recovered records.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(Orchestration).where(Orchestration.status == "analyzing")
        )
        stale = result.scalars().all()
        if not stale:
            return 0

        for orch in stale:
            orch.status = "pending_confirm"
            orch.error = "系统重启后恢复：LLM 分析未完成，请重新编排"
            await sync_todos_for_orchestration(db, orch.id)

        await db.commit()
        logger.warning("Recovered {} stale analyzing orchestration(s)", len(stale))
        return len(stale)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.post("/submit")
async def submit_orchestration(
    payload: SubmitPayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not payload.todo_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个待办任务")

    orch_id = f"orch-{uuid.uuid4().hex[:8]}"
    now = utc_now_naive()

    result = await db.execute(select(Todo).where(Todo.id.in_(payload.todo_ids)))
    todos = result.scalars().all()

    if not todos:
        raise HTTPException(status_code=400, detail="未找到对应的待办任务")
    if not getattr(current_user, "is_superuser", False):
        unauthorized = [todo.title for todo in todos if not _can_access_todo(current_user, todo)]
        if unauthorized:
            raise HTTPException(status_code=403, detail="仅可编排自己创建的待办任务")

    if not todos:
        raise HTTPException(status_code=400, detail="未找到对应的待办任务")

    user_execution_todos = [
        todo.title
        for todo in todos
        if getattr(todo, "execution_mode", "system") == "user"
    ]
    if user_execution_todos:
        raise HTTPException(status_code=400, detail="用户执行任务不能提交系统编排")

    invalid_status_todos = [
        todo.title
        for todo in todos
        if getattr(todo, "status", "pending") not in {"pending", "pending_confirm"}
    ]
    if invalid_status_todos:
        raise HTTPException(status_code=400, detail="仅待确认的系统执行任务可提交编排")

    todo_list = [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "source": t.source or "manual",
            "priority": t.priority or "medium",
            "status": t.status or "pending",
            "deadline": t.due_date.isoformat() if t.due_date else None,
            "created_at": t.created_at.isoformat() if t.created_at else now.isoformat(),
            "updated_at": t.updated_at.isoformat() if t.updated_at else now.isoformat(),
            "is_recurring": bool(getattr(t, "is_recurring", False)),
            "recurrence_cron": getattr(t, "recurrence_cron", None),
            "recurrence_count": int(getattr(t, "recurrence_count", 0) or 0),
        }
        for t in todos
    ]

    summary = build_orchestration_summary(todos)
    recurrence_defaults = _build_recurrence_defaults_from_todos(todos)

    for todo in todos:
        todo.status = "orchestrating"
        todo.orchestration_id = orch_id
    await db.flush()

    orch = Orchestration(
        id=orch_id,
        user_id=current_user.id if hasattr(current_user, "id") else None,
        summary=summary,
        status="analyzing",
        submitted_at=now,
        todos_snapshot=todo_list,
    )
    db.add(orch)
    await db.flush()

    # Commit early so the frontend can see "analyzing" status immediately,
    # then run the potentially slow LLM analysis in a background task.
    await db.commit()

    _launch_analysis(orch_id, payload.todo_ids, recurrence_defaults)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "orch_id": orch_id,
            "status": "analyzing",
        },
    }


@router.get("/pending")
async def list_pending_orchestrations(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Orchestration).where(Orchestration.status != "cancelled")
    )
    orchestrations = result.scalars().all()
    if not getattr(current_user, "is_superuser", False):
        orchestrations = [o for o in orchestrations if _can_access_orchestration(current_user, o)]

    items = []
    for orch in orchestrations:
        plan = orch.plan or {}
        rec_name = ""
        if orch.suggested_agent:
            rec_name = orch.suggested_agent.get("name", "")
        elif orch.suggested_wagent:
            rec_name = orch.suggested_wagent.get("name", "")
        elif plan.get("recommended_name"):
            rec_name = plan.get("recommended_name")

        item = {
            "orch_id": orch.id,
            "summary": build_orchestration_summary(
                orch.todos_snapshot or [], orch.summary or "未命名任务"
            ),
            "todos_count": len(orch.todos_snapshot or []),
            "status": orch.status or "pending_confirm",
            "submitted_at": (
                orch.submitted_at.isoformat() if orch.submitted_at else None
            ),
            "error": orch.error,
            "recommended_name": rec_name,
        }
        items.append(_convert_times_to_beijing(item))
    items.sort(key=lambda x: x.get("submitted_at") or "", reverse=True)
    return {"code": 200, "message": "success", "data": items}


@router.get("/{orch_id}")
async def get_orchestration_detail(
    orch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    orch = await db.get(Orchestration, orch_id)
    if not orch:
        raise HTTPException(status_code=404, detail="编排不存在")
    if not _can_access_orchestration(current_user, orch):
        raise HTTPException(status_code=403, detail="无权查看该编排")
    _snapshot_llm_recommendation(orch)
    _restore_plan_input_params_from_snapshot(orch)
    return {
        "code": 200,
        "message": "success",
        "data": _convert_times_to_beijing(orch.to_dict()),
    }


@router.post("/{orch_id}/confirm")
async def confirm_orchestration(
    orch_id: str,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    orch = await db.get(Orchestration, orch_id)
    if not orch:
        raise HTTPException(status_code=404, detail="编排不存在")
    if not _can_access_orchestration(current_user, orch):
        raise HTTPException(status_code=403, detail="无权操作该编排")
    previous_status = orch.status or "pending_confirm"
    if payload:
        plan = dict(orch.plan or {})
        incoming_params = payload.get("input_params")
        plan["input_params"] = (
            incoming_params if incoming_params else plan.get("input_params", {})
        )
        plan["priority"] = payload.get("priority", plan.get("priority"))
        plan["estimated_duration_minutes"] = payload.get(
            "estimated_duration_minutes", plan.get("estimated_duration_minutes")
        )
        plan["start_time"] = (
            _normalize_plan_time_value(payload.get("start_time"))
            or plan.get("start_time")
        )
        plan["deadline"] = (
            _normalize_plan_time_value(payload.get("deadline"))
            or plan.get("deadline")
        )
        if "is_recurring" in payload:
            plan["is_recurring"] = payload.get("is_recurring")
        if "recurrence_cron" in payload:
            plan["recurrence_cron"] = payload.get("recurrence_cron")
        if "recurrence_count" in payload:
            plan["recurrence_count"] = payload.get("recurrence_count")
        orch.plan = _apply_recurrence_to_plan(plan, _normalize_recurrence_payload(plan))
    else:
        orch.plan = _apply_recurrence_to_plan(
            orch.plan, _normalize_recurrence_payload(orch.plan or {})
        )
    try:
        await ensure_schedule_for_orchestration(db, orch_id, orch)
        await rebalance_schedule_tasks(db)
        recurrence_sync_warning = await _sync_todo_recurrence_for_orchestration(db, orch)
        orch.status = "confirmed"
        await sync_todos_for_orchestration(db, orch_id)
        return {
            "code": 200,
            "message": "success",
            "data": {"status": "confirmed", "recurrence_sync_warning": recurrence_sync_warning},
        }
    except Exception:
        orch.status = previous_status
        raise


@router.post("/{orch_id}/confirm-wagent")
async def confirm_wagent(
    orch_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    orch = await db.get(Orchestration, orch_id)
    if not orch:
        raise HTTPException(status_code=404, detail="编排不存在")
    if not _can_access_orchestration(current_user, orch):
        raise HTTPException(status_code=403, detail="无权操作该编排")
    previous_status = orch.status or "pending_confirm"
    if payload:
        plan = dict(orch.plan or {})
        incoming_params = payload.get("input_params")
        plan["input_params"] = (
            incoming_params if incoming_params else plan.get("input_params", {})
        )
        plan["priority"] = payload.get("priority", plan.get("priority"))
        plan["estimated_duration_minutes"] = payload.get(
            "estimated_duration_minutes", plan.get("estimated_duration_minutes")
        )
        plan["start_time"] = (
            _normalize_plan_time_value(payload.get("start_time"))
            or plan.get("start_time")
        )
        plan["deadline"] = (
            _normalize_plan_time_value(payload.get("deadline"))
            or plan.get("deadline")
        )
        if "is_recurring" in payload:
            plan["is_recurring"] = payload.get("is_recurring")
        if "recurrence_cron" in payload:
            plan["recurrence_cron"] = payload.get("recurrence_cron")
        if "recurrence_count" in payload:
            plan["recurrence_count"] = payload.get("recurrence_count")
        orch.plan = _apply_recurrence_to_plan(plan, _normalize_recurrence_payload(plan))
    else:
        orch.plan = _apply_recurrence_to_plan(
            orch.plan, _normalize_recurrence_payload(orch.plan or {})
        )
    try:
        await ensure_schedule_for_orchestration(db, orch_id, orch)
        await rebalance_schedule_tasks(db)
        recurrence_sync_warning = await _sync_todo_recurrence_for_orchestration(db, orch)
        orch.status = "confirmed"
        await sync_todos_for_orchestration(db, orch_id)
        return {
            "code": 200,
            "message": "success",
            "data": {"status": "confirmed", "recurrence_sync_warning": recurrence_sync_warning},
        }
    except Exception:
        orch.status = previous_status
        raise


@router.patch("/{orch_id}/modify-agent")
async def modify_agent(
    orch_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    orch = await db.get(Orchestration, orch_id)
    if not orch:
        raise HTTPException(status_code=404, detail="编排不存在")
    if not _can_access_orchestration(current_user, orch):
        raise HTTPException(status_code=403, detail="无权操作该编排")

    _snapshot_llm_recommendation(orch)

    plan_type = (
        payload.get("plan_type")
        or (orch.plan or {}).get("plan_type")
        or "agent"
    )
    recommended_id = payload.get("recommended_id")
    selected_name = payload.get("recommended_name")

    if plan_type == "agent":
        target = await db.get(Agent, recommended_id) if recommended_id else None
        if recommended_id and not target:
            raise HTTPException(status_code=404, detail="Agent 不存在")
        selected_name = selected_name or (target.name if target else "")
    elif plan_type in {"wagent", "new_wagent"}:
        target = await db.get(WAgent, recommended_id) if recommended_id else None
        if recommended_id and not target:
            raise HTTPException(status_code=404, detail="W-Agent 不存在")
        selected_name = selected_name or (target.name if target else "")
    else:
        raise HTTPException(status_code=400, detail="不支持的执行器类型")

    _apply_selected_executor(orch, plan_type, recommended_id, selected_name)
    if plan_type == "agent":
        plan = dict(orch.plan or {})
        raw_schema = getattr(target, "input_params", {}) if target else {}
        rebuilt_params, editable_keys = _build_plan_input_params_for_selected_agent(
            raw_schema or {}
        )
        if (
            recommended_id
            and recommended_id == orch.llm_recommended_id
            and orch.llm_recommended_type == "agent"
        ):
            llm_snapshot_params = orch.llm_recommended_input_params
            if isinstance(llm_snapshot_params, dict) and llm_snapshot_params:
                if not editable_keys:
                    editable_keys = list(llm_snapshot_params.keys())
                    rebuilt_params = {
                        key: llm_snapshot_params.get(key) for key in editable_keys
                    }
                else:
                    for key in editable_keys:
                        if key in llm_snapshot_params:
                            rebuilt_params[key] = llm_snapshot_params[key]
        plan["editable_input_keys"] = editable_keys
        plan["input_params"] = rebuilt_params
        orch.plan = plan
    return {
        "code": 200,
        "message": "success",
        "data": _convert_times_to_beijing(orch.to_dict()),
    }


@router.patch("/{orch_id}/modify-params")
async def modify_params(
    orch_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    orch = await db.get(Orchestration, orch_id)
    if not orch:
        raise HTTPException(status_code=404, detail="编排不存在")
    if not _can_access_orchestration(current_user, orch):
        raise HTTPException(status_code=403, detail="无权操作该编排")
    plan = dict(orch.plan or {})
    if "input_params" in payload:
        plan["input_params"] = payload["input_params"]
    if "priority" in payload:
        plan["priority"] = payload["priority"]
    if "estimated_duration_minutes" in payload:
        plan["estimated_duration_minutes"] = payload["estimated_duration_minutes"]
    if "start_time" in payload:
        plan["start_time"] = _normalize_plan_time_value(payload["start_time"])
    if "deadline" in payload:
        plan["deadline"] = _normalize_plan_time_value(payload["deadline"])
    if "is_recurring" in payload:
        plan["is_recurring"] = payload["is_recurring"]
    if "recurrence_cron" in payload:
        plan["recurrence_cron"] = payload["recurrence_cron"]
    if "recurrence_count" in payload:
        plan["recurrence_count"] = payload["recurrence_count"]
    orch.plan = _apply_recurrence_to_plan(plan, _normalize_recurrence_payload(plan))
    recurrence_sync_warning = await _sync_todo_recurrence_for_orchestration(db, orch)
    response_data = _convert_times_to_beijing(orch.to_dict())
    if recurrence_sync_warning:
        response_data["recurrence_sync_warning"] = recurrence_sync_warning
    return {
        "code": 200,
        "message": "success",
        "data": response_data,
    }


@router.post("/{orch_id}/cancel")
async def cancel_orchestration(
    orch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    orch = await db.get(Orchestration, orch_id)
    if not orch:
        raise HTTPException(status_code=404, detail="编排不存在")
    if not _can_access_orchestration(current_user, orch):
        raise HTTPException(status_code=403, detail="无权操作该编排")

    await sync_todos_for_orchestration(db, orch_id, status_override="cancelled")
    await _cancel_schedule_for_orchestration(db, orch_id)
    await db.delete(orch)
    await db.flush()
    await _broadcast_orchestration_complete(orch_id, "cancelled", removed=True)
    return {
        "code": 200,
        "message": "success",
        "data": {"status": "cancelled", "removed": True},
    }


@router.post("/{orch_id}/retry")
async def retry_orchestration(
    orch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    orch = await db.get(Orchestration, orch_id)
    if not orch:
        raise HTTPException(status_code=404, detail="编排不存在")
    if not _can_access_orchestration(current_user, orch):
        raise HTTPException(status_code=403, detail="无权操作该编排")
    if orch.status not in ("pending_confirm", "failed", "cancelled"):
        raise HTTPException(
            status_code=400, detail="仅待确认、失败或已取消的编排可以重新编排"
        )

    todo_ids = [t.get("id") for t in (orch.todos_snapshot or []) if t.get("id")]
    if not todo_ids:
        raise HTTPException(status_code=400, detail="编排中没有待办任务")

    orch.status = "analyzing"
    orch.error = None
    orch.plan = None
    orch.llm_reason = None
    orch.suggested_agent = None
    orch.suggested_wagent = None

    await db.commit()

    _launch_analysis(orch_id, todo_ids, _normalize_recurrence_payload(None))

    return {
        "code": 200,
        "message": "success",
        "data": {
            "orch_id": orch_id,
            "status": "analyzing",
        },
    }
