import json as _json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.orchestrator import orchestrator
from app.models import Todo, SchedulePlan, ScheduleTask
from app.services.sse_manager import sse_manager
from loguru import logger

router = APIRouter(prefix="/orchestration", tags=["orchestration"])

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DATA_DIR.mkdir(exist_ok=True)
_STORE_FILE = _DATA_DIR / "orchestrations.json"

_orchestration_store: dict[str, dict] = {}


def _prune_cancelled_orchestrations() -> list[str]:
    removed_ids = [
        orch_id
        for orch_id, entry in list(_orchestration_store.items())
        if entry.get("status") == "cancelled"
    ]
    for orch_id in removed_ids:
        _orchestration_store.pop(orch_id, None)
    return removed_ids


def _load_store():
    global _orchestration_store
    if _STORE_FILE.exists():
        try:
            _orchestration_store = _json.loads(_STORE_FILE.read_text(encoding="utf-8"))
            removed_ids = _prune_cancelled_orchestrations()
            if removed_ids:
                logger.info(f"Pruned {len(removed_ids)} cancelled orchestrations while loading store")
                _save_store()
            logger.info(f"Loaded {len(_orchestration_store)} orchestrations from {_STORE_FILE}")
            return
        except Exception as e:
            logger.warning(f"Failed to load orchestration store: {e}")
    _orchestration_store = {}


def _save_store():
    removed_ids = _prune_cancelled_orchestrations()
    if removed_ids:
        logger.info(f"Pruned {len(removed_ids)} cancelled orchestrations before saving store")
    try:
        _STORE_FILE.write_text(
            _json.dumps(_orchestration_store, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"Failed to save orchestration store: {e}")


async def _broadcast_orchestration_complete(orch_id: str, status: str, error: str | None = None, removed: bool = False) -> None:
    await sse_manager.broadcast(
        "orchestration_complete",
        {
            "orch_id": orch_id,
            "status": status,
            "error": error,
            "removed": removed,
        },
    )


class SubmitPayload(BaseModel):
    todo_ids: list[str]


MOCK_DETAILS = {
    "orch-a1b2c3": {
        "orch_id": "orch-a1b2c3",
        "summary": "审计2025年Q4财务报表 等3个任务",
        "status": "pending_confirm",
        "submitted_at": "2026-03-04T09:00:00",
        "todos": [
            {
                "id": "todo-001",
                "title": "审计2025年Q4财务报表",
                "source": "email",
                "priority": "high",
                "status": "pending",
                "deadline": "2026-03-15T18:00:00",
                "created_at": "2026-03-01T09:00:00",
                "updated_at": "2026-03-01T09:00:00",
            },
            {
                "id": "todo-002",
                "title": "核查供应商合同合规性",
                "source": "calendar",
                "priority": "medium",
                "status": "pending",
                "deadline": "2026-03-20T18:00:00",
                "created_at": "2026-03-01T09:30:00",
                "updated_at": "2026-03-01T09:30:00",
            },
            {
                "id": "todo-003",
                "title": "整理内部控制流程文档",
                "source": "project_progress",
                "priority": "low",
                "status": "pending",
                "deadline": "2026-03-25T18:00:00",
                "created_at": "2026-03-01T10:00:00",
                "updated_at": "2026-03-01T10:00:00",
            },
        ],
        "suggested_agent": {
            "id": "agent-fin-001",
            "name": "财务审计Agent",
            "type": "dify_agent",
            "is_enabled": True,
        },
        "suggested_wagent": None,
        "plan": {
            "plan_type": "agent",
            "recommended_id": "agent-fin-001",
            "recommended_name": "财务审计Agent",
            "reason": "该批次包含财务报表审计和合同合规核查任务，财务审计Agent具备报表分析、合规检查等能力，适合统一处理。",
            "input_params": {
                "audit_period": "2025-Q4",
                "report_type": "financial_statement",
                "compliance_standard": "CAS",
            },
            "priority": "high",
            "estimated_duration_minutes": 120,
        },
        "llm_reason": "经分析，3个待办任务均与财务审计相关：Q4财务报表审计为核心任务（高优先级），供应商合同合规检查和内控文档整理为辅助任务。推荐使用「财务审计Agent」统一处理，预计耗时约2小时。建议优先完成报表审计，再进行合规核查。",
    },
    "orch-d4e5f6": {
        "orch_id": "orch-d4e5f6",
        "summary": "自动化生成月度合规报告",
        "status": "pending_confirm",
        "submitted_at": "2026-03-04T08:30:00",
        "todos": [
            {
                "id": "todo-004",
                "title": "自动化生成月度合规报告",
                "source": "project_progress",
                "priority": "medium",
                "status": "pending",
                "deadline": "2026-03-10T18:00:00",
                "created_at": "2026-03-02T08:00:00",
                "updated_at": "2026-03-02T08:00:00",
            },
        ],
        "suggested_agent": None,
        "suggested_wagent": {
            "id": "wagent-report-001",
            "name": "报告生成W-Agent",
            "is_enabled": True,
        },
        "plan": {
            "plan_type": "new_wagent",
            "recommended_id": "wagent-report-001",
            "recommended_name": "报告生成W-Agent",
            "reason": "月度合规报告需要多步骤流程：数据采集→合规检查→报告生成→格式化输出。推荐使用W-Agent编排工作流执行。",
            "input_params": {
                "report_month": "2026-02",
                "template": "monthly_compliance",
                "output_format": "pdf",
            },
            "priority": "medium",
            "estimated_duration_minutes": 45,
            "steps": [
                {"order": 1, "workflow_name": "数据采集与清洗"},
                {"order": 2, "workflow_name": "合规规则检查"},
                {"order": 3, "workflow_name": "报告内容生成"},
                {"order": 4, "workflow_name": "PDF格式化输出"},
            ],
        },
        "llm_reason": "该任务需要生成月度合规报告，涉及数据采集、规则检查、内容生成和格式化输出4个步骤。推荐创建新的W-Agent工作流来编排执行，各步骤串行完成，预计耗时45分钟。",
    },
}

_load_store()

if not _orchestration_store:
    for _k, _v in MOCK_DETAILS.items():
        _orchestration_store[_k] = _v
    _save_store()


def update_orchestration_status(orch_id: str, status: str, error: str | None = None) -> bool:
    if orch_id in _orchestration_store:
        _orchestration_store[orch_id]["status"] = status
        if error:
            _orchestration_store[orch_id]["error"] = error
        _save_store()
        return True
    return False


def get_orchestration_entry(orch_id: str) -> dict | None:
    return _orchestration_store.get(orch_id)


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


def map_orchestration_status_to_todo_status(status: str | None) -> str:
    if status in {"analyzing", "pending_confirm", "failed"}:
        return "orchestrating"
    if status == "confirmed":
        return "scheduling"
    if status == "completed":
        return "completed"
    return "pending_confirm"


async def sync_todos_for_orchestration(db: AsyncSession, orch_id: str, entry: dict | None = None) -> None:
    target_entry = entry or _orchestration_store.get(orch_id)
    if not target_entry:
        return

    todo_ids = [item.get("id") for item in target_entry.get("todos", []) if item.get("id")]
    if not todo_ids:
        return

    result = await db.execute(select(Todo).where(Todo.id.in_(todo_ids)))
    todos = result.scalars().all()
    orchestration_status = target_entry.get("status")
    todo_status = map_orchestration_status_to_todo_status(orchestration_status)
    should_clear_orchestration_id = orchestration_status == "cancelled"

    for todo in todos:
        todo.status = todo_status
        todo.orchestration_id = None if should_clear_orchestration_id else orch_id

    await db.flush()


def _normalize_plan_time_value(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    else:
        parsed = parsed.replace(microsecond=0)
    return parsed.replace(microsecond=0).isoformat()


def _parse_schedule_datetime(value: str | None) -> datetime:
    normalized = _normalize_plan_time_value(value)
    if not normalized:
        return datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    try:
        return datetime.fromisoformat(normalized).replace(microsecond=0)
    except ValueError:
        return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


async def _cancel_schedule_for_orchestration(db: AsyncSession, orch_id: str) -> None:
    existing_task_result = await db.execute(
        select(ScheduleTask).where(ScheduleTask.orchestration_id == orch_id)
    )
    schedule_tasks = existing_task_result.scalars().all()
    if not schedule_tasks:
        return

    plan_ids = {task.plan_id for task in schedule_tasks if task.plan_id}
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)

    for task in schedule_tasks:
        task.status = "cancelled"
        task.error_message = task.error_message or "编排已取消"
        if task.completed_at is None:
            task.completed_at = now

    if plan_ids:
        plans_result = await db.execute(select(SchedulePlan).where(SchedulePlan.id.in_(plan_ids)))
        for plan in plans_result.scalars().all():
            plan.status = "cancelled"

    await db.flush()


async def ensure_schedule_for_orchestration(db: AsyncSession, orch_id: str, entry: dict) -> None:
    plan_data = entry.get("plan") or {}
    existing_task_result = await db.execute(
        select(ScheduleTask).where(ScheduleTask.orchestration_id == orch_id)
    )
    schedule_task = existing_task_result.scalar_one_or_none()

    schedule_plan = None
    if schedule_task:
        schedule_plan = await db.get(SchedulePlan, schedule_task.plan_id)

    if schedule_plan is None:
        schedule_plan = SchedulePlan(
            name=entry.get("summary") or f"编排任务 {orch_id}",
            status="active",
            is_recurring=False,
        )
        db.add(schedule_plan)
        await db.flush()

    recommended_id = plan_data.get("recommended_id")
    plan_type = plan_data.get("plan_type")
    agent_id = recommended_id if plan_type == "agent" and recommended_id else None
    wagent_id = recommended_id if plan_type in ("wagent", "new_wagent") and recommended_id else None
    scheduled_at = _parse_schedule_datetime(plan_data.get("start_time"))

    if schedule_task is None:
        schedule_task = ScheduleTask(
            plan_id=schedule_plan.id,
            orchestration_id=orch_id,
            agent_id=agent_id,
            wagent_id=wagent_id,
            status="pending",
            priority=plan_data.get("priority") or "medium",
            scheduled_at=scheduled_at,
            input_params=plan_data.get("input_params") or {},
        )
        db.add(schedule_task)
    else:
        schedule_task.plan_id = schedule_plan.id
        schedule_task.agent_id = agent_id
        schedule_task.wagent_id = wagent_id
        schedule_task.status = "pending"
        schedule_task.priority = plan_data.get("priority") or schedule_task.priority or "medium"
        schedule_task.scheduled_at = scheduled_at
        schedule_task.input_params = plan_data.get("input_params") or {}
        schedule_task.error_message = None

    schedule_plan.name = entry.get("summary") or schedule_plan.name
    schedule_plan.status = "active"
    await db.flush()


@router.post("/submit")
async def submit_orchestration(
    payload: SubmitPayload,
    db: AsyncSession = Depends(get_db),
):
    if not payload.todo_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个待办任务")

    orch_id = f"orch-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(tzinfo=None).isoformat()

    result = await db.execute(select(Todo).where(Todo.id.in_(payload.todo_ids)))
    todos = result.scalars().all()

    if not todos:
        raise HTTPException(status_code=400, detail="未找到对应的待办任务")

    user_execution_todos = [todo.title for todo in todos if getattr(todo, "execution_mode", "system") == "user"]
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
            "created_at": t.created_at.isoformat() if t.created_at else now,
            "updated_at": t.updated_at.isoformat() if t.updated_at else now,
        }
        for t in todos
    ]

    summary = build_orchestration_summary(todos)

    # Update todos status to orchestrating
    for todo in todos:
        todo.status = "orchestrating"
        todo.orchestration_id = orch_id
    await db.flush()

    entry = {
        "orch_id": orch_id,
        "summary": summary,
        "status": "analyzing",
        "submitted_at": now,
        "todos": todo_list,
        "suggested_agent": None,
        "suggested_wagent": None,
        "plan": None,
        "llm_reason": None,
        "error": None,
    }
    _orchestration_store[orch_id] = entry

    try:
        plan_result = await orchestrator.orchestrate(db, payload.todo_ids)

        if "error" in plan_result:
            entry["status"] = "failed"
            entry["error"] = plan_result["error"]
        else:
            entry["status"] = plan_result.get("status", "pending_confirm")
            entry["plan"] = plan_result.get("plan")
            entry["llm_reason"] = plan_result.get("llm_reason")

            plan = plan_result.get("plan", {})
            if plan and plan.get("plan_type") in ("agent",):
                rec_id = plan.get("recommended_id")
                rec_name = plan.get("recommended_name", "")
                entry["suggested_agent"] = {"id": rec_id, "name": rec_name, "is_enabled": True} if rec_id else None
            elif plan and plan.get("plan_type") in ("wagent", "new_wagent"):
                rec_id = plan.get("recommended_id")
                rec_name = plan.get("recommended_name", "")
                entry["suggested_wagent"] = {"id": rec_id, "name": rec_name, "is_enabled": True} if rec_id else None

    except Exception as e:
        logger.error(f"Orchestration failed for {orch_id}: {e}")
        entry["status"] = "failed"
        entry["error"] = f"编排分析失败: {str(e)}"

    await sync_todos_for_orchestration(db, orch_id, entry)
    _save_store()
    await _broadcast_orchestration_complete(orch_id, entry["status"], entry.get("error"))
    return {
        "code": 200,
        "message": "success",
        "data": {"orch_id": orch_id, "status": entry["status"], "error": entry.get("error")},
    }


@router.get("/pending")
async def list_pending_orchestrations(
    db: AsyncSession = Depends(get_db),
):
    if _prune_cancelled_orchestrations():
        _save_store()
    items = []
    for orch_id, entry in _orchestration_store.items():
        plan = entry.get("plan") or {}
        rec_name = ""
        if entry.get("suggested_agent"):
             rec_name = entry["suggested_agent"]["name"]
        elif entry.get("suggested_wagent"):
             rec_name = entry["suggested_wagent"]["name"]
        elif plan.get("recommended_name"):
             rec_name = plan.get("recommended_name")

        items.append({
            "orch_id": orch_id,
            "summary": build_orchestration_summary(entry.get("todos", []), entry.get("summary", "未命名任务")),
            "todos_count": len(entry.get("todos", [])),
            "status": entry.get("status", "pending_confirm"),
            "submitted_at": entry.get("submitted_at"),
            "error": entry.get("error"),
            "recommended_name": rec_name,
        })
    items.sort(key=lambda x: x.get("submitted_at") or "", reverse=True)
    return {
        "code": 200,
        "message": "success",
        "data": items,
    }


@router.get("/{orch_id}")
async def get_orchestration_detail(
    orch_id: str,
    db: AsyncSession = Depends(get_db),
):
    entry = _orchestration_store.get(orch_id)
    if not entry:
        raise HTTPException(status_code=404, detail="编排不存在")
    return {
        "code": 200,
        "message": "success",
        "data": entry,
    }


@router.post("/{orch_id}/confirm")
async def confirm_orchestration(
    orch_id: str,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
):
    entry = _orchestration_store.get(orch_id)
    if not entry:
        raise HTTPException(status_code=404, detail="编排不存在")
    entry["status"] = "confirmed"
    if payload:
        plan = entry.get("plan") or {}
        plan["input_params"] = payload.get("input_params", plan.get("input_params"))
        plan["priority"] = payload.get("priority", plan.get("priority"))
        plan["estimated_duration_minutes"] = payload.get("estimated_duration_minutes", plan.get("estimated_duration_minutes"))
        plan["start_time"] = _normalize_plan_time_value(payload.get("start_time")) or plan.get("start_time")
        plan["deadline"] = _normalize_plan_time_value(payload.get("deadline")) or plan.get("deadline")
        entry["plan"] = plan
    await ensure_schedule_for_orchestration(db, orch_id, entry)
    await sync_todos_for_orchestration(db, orch_id, entry)
    _save_store()
    return {"code": 200, "message": "success", "data": {"status": "confirmed"}}


@router.post("/{orch_id}/confirm-wagent")
async def confirm_wagent(
    orch_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    entry = _orchestration_store.get(orch_id)
    if not entry:
        raise HTTPException(status_code=404, detail="编排不存在")
    entry["status"] = "confirmed"
    if payload:
        plan = entry.get("plan") or {}
        plan["input_params"] = payload.get("input_params", plan.get("input_params"))
        plan["priority"] = payload.get("priority", plan.get("priority"))
        plan["estimated_duration_minutes"] = payload.get("estimated_duration_minutes", plan.get("estimated_duration_minutes"))
        plan["start_time"] = _normalize_plan_time_value(payload.get("start_time")) or plan.get("start_time")
        plan["deadline"] = _normalize_plan_time_value(payload.get("deadline")) or plan.get("deadline")
        entry["plan"] = plan
    await ensure_schedule_for_orchestration(db, orch_id, entry)
    await sync_todos_for_orchestration(db, orch_id, entry)
    _save_store()
    return {"code": 200, "message": "success", "data": {"status": "confirmed"}}


@router.patch("/{orch_id}/modify-agent")
async def modify_agent(
    orch_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    entry = _orchestration_store.get(orch_id)
    if not entry:
        raise HTTPException(status_code=404, detail="编排不存在")
    plan = entry.get("plan") or {}
    plan["plan_type"] = payload.get("plan_type", plan.get("plan_type"))
    plan["recommended_id"] = payload.get("recommended_id", plan.get("recommended_id"))
    plan["recommended_name"] = payload.get("recommended_name", plan.get("recommended_name"))
    entry["plan"] = plan
    _save_store()
    return {"code": 200, "message": "success", "data": entry}


@router.patch("/{orch_id}/modify-params")
async def modify_params(
    orch_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    entry = _orchestration_store.get(orch_id)
    if not entry:
        raise HTTPException(status_code=404, detail="编排不存在")
    plan = entry.get("plan") or {}
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
    entry["plan"] = plan
    _save_store()
    return {"code": 200, "message": "success", "data": entry}


@router.post("/{orch_id}/cancel")
async def cancel_orchestration(
    orch_id: str,
    db: AsyncSession = Depends(get_db),
):
    entry = _orchestration_store.get(orch_id)
    if not entry:
        raise HTTPException(status_code=404, detail="编排不存在")

    cancelled_entry = dict(entry)
    cancelled_entry["status"] = "cancelled"
    await sync_todos_for_orchestration(db, orch_id, cancelled_entry)
    await _cancel_schedule_for_orchestration(db, orch_id)
    _orchestration_store.pop(orch_id, None)
    _save_store()
    await _broadcast_orchestration_complete(orch_id, "cancelled", removed=True)
    return {"code": 200, "message": "success", "data": {"status": "cancelled", "removed": True}}


@router.post("/{orch_id}/retry")
async def retry_orchestration(
    orch_id: str,
    db: AsyncSession = Depends(get_db),
):
    entry = _orchestration_store.get(orch_id)
    if not entry:
        raise HTTPException(status_code=404, detail="编排不存在")
    if entry["status"] not in ("pending_confirm", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail="仅待确认、失败或已取消的编排可以重新编排")

    todo_ids = [t["id"] for t in entry.get("todos", [])]
    if not todo_ids:
        raise HTTPException(status_code=400, detail="编排中没有待办任务")

    entry["status"] = "analyzing"
    entry["error"] = None
    entry["plan"] = None
    entry["llm_reason"] = None
    entry["suggested_agent"] = None
    entry["suggested_wagent"] = None

    try:
        plan_result = await orchestrator.orchestrate(db, todo_ids)

        if "error" in plan_result:
            entry["status"] = "failed"
            entry["error"] = plan_result["error"]
        else:
            entry["status"] = plan_result.get("status", "pending_confirm")
            entry["plan"] = plan_result.get("plan")
            entry["llm_reason"] = plan_result.get("llm_reason")

            plan = plan_result.get("plan", {})
            if plan and plan.get("plan_type") in ("agent",):
                rec_id = plan.get("recommended_id")
                rec_name = plan.get("recommended_name", "")
                entry["suggested_agent"] = {"id": rec_id, "name": rec_name, "is_enabled": True} if rec_id else None
            elif plan and plan.get("plan_type") in ("wagent", "new_wagent"):
                rec_id = plan.get("recommended_id")
                rec_name = plan.get("recommended_name", "")
                entry["suggested_wagent"] = {"id": rec_id, "name": rec_name, "is_enabled": True} if rec_id else None

    except Exception as e:
        logger.error(f"Orchestration retry failed for {orch_id}: {e}")
        entry["status"] = "failed"
        entry["error"] = f"重新编排失败: {str(e)}"

    await sync_todos_for_orchestration(db, orch_id, entry)
    _save_store()
    await _broadcast_orchestration_complete(orch_id, entry["status"], entry.get("error"))
    return {
        "code": 200,
        "message": "success",
        "data": {"orch_id": orch_id, "status": entry["status"], "error": entry.get("error")},
    }
