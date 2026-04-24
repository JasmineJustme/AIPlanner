from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from app.utils.recurrence import normalize_cron_expression, validate_cron_expression
from sqlalchemy import select, func, or_
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.engine.todo_discovery import todo_discovery_engine
from app.models import Message, Todo, ScheduleTask, TodoFlowLog
from app.services.llm_client import LLMServiceError
from app.utils.timezone import to_utc_naive, utc_now_naive
from pydantic import BaseModel
from app.schemas.todo import TodoCreate, TodoUpdate, TodoResponse, TodoReviewConfirm


async def _sync_origin_flow_completion(db: AsyncSession, todo: Todo, current_user_id: str | None) -> None:
    if not todo.original_owner_id or todo.original_owner_id == (todo.owner_id or current_user_id):
        return
    if todo.status != "completed":
        return
    before_flow_state = todo.last_flow_state
    todo.last_flow_state = "completed"
    db.add(
        Message(
            type="task_completed",
            title=todo.title,
            content=f"目标账户已完成任务：{todo.title}",
            status="unread",
            related_type="todo",
            related_id=todo.id,
            recipient_user_id=todo.original_owner_id,
            sender_user_id=current_user_id or todo.owner_id,
        )
    )
    db.add(
        TodoFlowLog(
            todo_id=todo.id,
            action_type="complete",
            from_user_id=current_user_id or todo.owner_id,
            to_user_id=todo.original_owner_id,
            status_before="pending",
            status_after="completed",
            flow_state_before=before_flow_state,
            flow_state_after="completed",
            remark="目标账户已完成任务，原账户只读状态更新为已完成",
        )
    )


class BatchIdsBody(BaseModel):
    todo_ids: list[str] = []


router = APIRouter(prefix="/todos", tags=["todos"])


def _normalize_todo_time_fields(data: dict) -> dict:
    normalized = dict(data)
    for key in ("due_date", "completed_at"):
        if key in normalized and normalized[key] is not None:
            normalized[key] = to_utc_naive(normalized[key])
    return normalized


def _normalize_recurrence_fields(data: dict) -> dict:
    is_recurring = bool(data.get("is_recurring", False))
    normalized = dict(data)
    normalized["is_recurring"] = is_recurring
    if not is_recurring:
        normalized["recurrence_cron"] = None
        normalized["recurrence_count"] = 0
        return normalized

    recurrence_cron = normalize_cron_expression(data.get("recurrence_cron"))
    if not recurrence_cron or not validate_cron_expression(recurrence_cron):
        raise HTTPException(status_code=400, detail="循环表达式无效，请输入合法 cron")
    normalized["recurrence_cron"] = recurrence_cron
    normalized["recurrence_count"] = max(0, int(data.get("recurrence_count") or 0))
    return normalized


async def _reconcile_orchestration_todo_statuses(db: AsyncSession) -> None:
    from app.api.orchestration import map_orchestration_status_to_todo_status
    from app.models import Orchestration

    result = await db.execute(
        select(Todo).where(
            or_(
                Todo.orchestration_id.is_not(None),
                Todo.status.in_(["orchestrating", "scheduling"]),
            )
        )
    )
    items = result.scalars().all()
    changed = False
    now = utc_now_naive()

    orchestration_ids = list({todo.orchestration_id for todo in items if todo.orchestration_id})
    latest_completion_by_orch: dict[str, datetime] = {}
    if orchestration_ids:
        try:
            tasks_result = await db.execute(
                select(ScheduleTask).where(
                    ScheduleTask.orchestration_id.in_(orchestration_ids),
                    ScheduleTask.completed_at.is_not(None),
                )
            )
            for task in tasks_result.scalars().all():
                orch_id = str(task.orchestration_id or "")
                if not orch_id or task.completed_at is None:
                    continue
                prev = latest_completion_by_orch.get(orch_id)
                if prev is None or task.completed_at > prev:
                    latest_completion_by_orch[orch_id] = task.completed_at
        except OperationalError as exc:
            if "schedule_tasks" not in str(exc).lower():
                raise

    orch_map: dict[str, Orchestration] = {}
    if orchestration_ids:
        try:
            orch_result = await db.execute(
                select(Orchestration).where(Orchestration.id.in_(orchestration_ids))
            )
            for o in orch_result.scalars().all():
                orch_map[o.id] = o
        except OperationalError:
            pass

    for todo in items:
        orch = orch_map.get(todo.orchestration_id or "") if todo.orchestration_id else None
        if not orch:
            if todo.status != "pending_confirm" or todo.orchestration_id is not None or todo.completed_at is not None:
                todo.status = "pending_confirm"
                todo.orchestration_id = None
                todo.completed_at = None
                changed = True
            continue

        next_status = map_orchestration_status_to_todo_status(orch.status)
        if todo.status != next_status:
            todo.status = next_status
            changed = True
        if next_status == "completed":
            completed_at = latest_completion_by_orch.get(todo.orchestration_id or "")
            if todo.completed_at != (completed_at or now):
                todo.completed_at = completed_at or now
                changed = True
        elif todo.completed_at is not None:
            todo.completed_at = None
            changed = True

    if changed:
        await db.flush()


async def _get_todo_or_404(todo_id: str, db: AsyncSession, current_user=None) -> Todo:
    query = select(Todo).where(Todo.id == todo_id)
    if current_user is not None and not getattr(current_user, "is_superuser", False):
        query = query.where(or_(Todo.creator_id == current_user.id, Todo.owner_id == current_user.id))
    result = await db.execute(query)
    todo = result.scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo


@router.get("")
async def list_todos(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    priority: str | None = Query(None),
    source: str | None = Query(None),
    execution_mode: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _reconcile_orchestration_todo_statuses(db)
    offset = (page - 1) * size
    q = select(Todo)
    count_q = select(func.count()).select_from(Todo)
    if not getattr(current_user, "is_superuser", False):
        q = q.where(Todo.owner_id == current_user.id)
        count_q = count_q.where(Todo.owner_id == current_user.id)
    if status:
        q = q.where(Todo.status == status)
        count_q = count_q.where(Todo.status == status)
    if priority:
        q = q.where(Todo.priority == priority)
        count_q = count_q.where(Todo.priority == priority)
    if source:
        q = q.where(Todo.source == source)
        count_q = count_q.where(Todo.source == source)
    if execution_mode:
        q = q.where(Todo.execution_mode == execution_mode)
        count_q = count_q.where(Todo.execution_mode == execution_mode)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0
    result = await db.execute(q.offset(offset).limit(size).order_by(Todo.created_at.desc()))
    items = result.scalars().all()
    pages = (total + size - 1) // size if total > 0 else 0
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [TodoResponse.model_validate(i) for i in items],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        },
    }


@router.post("")
async def create_todo(
    payload: TodoCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    data = _normalize_todo_time_fields(_normalize_recurrence_fields(payload.model_dump()))
    creator_id = data.get("creator_id") or getattr(current_user, "id", None)
    todo = Todo(
        title=data["title"],
        description=data.get("description"),
        status="pending_confirm",
        priority=data.get("priority", "medium"),
        source=data.get("source", "manual"),
        execution_mode=data.get("execution_mode", "system"),
        creator_id=creator_id,
        owner_id=data.get("owner_id") or creator_id,
        original_owner_id=data.get("original_owner_id") or creator_id,
        target_user_id=data.get("target_user_id"),
        task_flow_type=data.get("task_flow_type") or ("system_execution" if data.get("execution_mode", "system") == "system" else "user_execution"),
        last_flow_state=data.get("last_flow_state"),
        last_flow_type=data.get("last_flow_type"),
        due_date=data.get("due_date"),
        tags=data.get("tags", []),
        responsibility_ids=data.get("responsibility_ids", []),
        responsibility_titles=data.get("responsibility_titles", []),
        project=data.get("project"),
        is_recurring=data.get("is_recurring", False),
        recurrence_cron=data.get("recurrence_cron"),
        recurrence_count=data.get("recurrence_count", 0),
    )
    db.add(todo)
    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.put("/{todo_id}")
async def update_todo(
    todo_id: str,
    payload: TodoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    todo = await _get_todo_or_404(todo_id, db, current_user)
    data = _normalize_todo_time_fields(payload.model_dump(exclude_unset=True))

    if "is_recurring" in data:
        data = _normalize_recurrence_fields({
            "is_recurring": data.get("is_recurring"),
            "recurrence_cron": data.get("recurrence_cron", todo.recurrence_cron),
            "recurrence_count": data.get("recurrence_count", todo.recurrence_count),
        }) | {k: v for k, v in data.items() if k not in {"is_recurring", "recurrence_cron", "recurrence_count"}}
    elif "recurrence_cron" in data or "recurrence_count" in data:
        data = _normalize_recurrence_fields(
            {
                "is_recurring": True,
                "recurrence_cron": data.get("recurrence_cron", todo.recurrence_cron),
                "recurrence_count": data.get("recurrence_count", todo.recurrence_count),
            }
        ) | {k: v for k, v in data.items() if k not in {"is_recurring", "recurrence_cron", "recurrence_count"}}

    for k, v in data.items():
        setattr(todo, k, v)

    if data.get("execution_mode") == "user":
        todo.orchestration_id = None
        if todo.status != "completed":
            todo.status = "pending"

    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.patch("/{todo_id}/complete")
async def complete_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    todo = await _get_todo_or_404(todo_id, db, current_user)
    if todo.execution_mode != "user":
        raise HTTPException(status_code=400, detail="仅用户执行任务支持手动完成")
    if todo.status not in {"pending", "pending_confirm"}:
        raise HTTPException(status_code=400, detail="仅待确认的用户执行任务支持手动完成")

    todo.status = "completed"
    todo.completed_at = utc_now_naive()
    todo.orchestration_id = None
    await _sync_origin_flow_completion(db, todo, getattr(current_user, "id", None))
    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.patch("/{todo_id}/confirm")
async def confirm_user_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    todo = await _get_todo_or_404(todo_id, db, current_user)
    if todo.execution_mode != "user":
        raise HTTPException(status_code=400, detail="仅用户执行任务支持确认")
    if todo.status != "pending_confirm":
        raise HTTPException(status_code=400, detail="仅待确认的用户执行任务支持确认")

    todo.status = "pending"
    todo.completed_at = None
    todo.orchestration_id = None
    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.patch("/{todo_id}/cancel")
async def cancel_user_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    todo = await _get_todo_or_404(todo_id, db, current_user)
    if todo.execution_mode != "user":
        raise HTTPException(status_code=400, detail="仅用户执行任务支持取消")
    if todo.status != "pending":
        raise HTTPException(status_code=400, detail="仅待处理的用户执行任务支持取消")

    todo.status = "pending_confirm"
    todo.completed_at = None
    todo.orchestration_id = None
    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.post("/{todo_id}/rerun")
async def rerun_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    todo = await _get_todo_or_404(todo_id, db, current_user)
    if todo.status != "completed":
        raise HTTPException(status_code=400, detail="仅已完成任务支持重新执行")

    new_todo = Todo(
        title=todo.title,
        description=todo.description,
        status="pending_confirm",
        priority=todo.priority,
        source=todo.source,
        execution_mode=todo.execution_mode,
        source_ref=todo.source_ref,
        due_date=todo.due_date,
        tags=list(todo.tags or []),
        responsibility_ids=list(todo.responsibility_ids or []),
        responsibility_titles=list(todo.responsibility_titles or []),
        project=todo.project,
        is_recurring=todo.is_recurring,
        recurrence_cron=todo.recurrence_cron,
        recurrence_count=todo.recurrence_count,
    )
    db.add(new_todo)
    await db.flush()
    await db.refresh(new_todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(new_todo)}


@router.delete("/{todo_id}")
async def delete_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    todo = await _get_todo_or_404(todo_id, db, current_user)
    await db.delete(todo)
    return {"code": 200, "message": "success", "data": None}


@router.post("/batch-import")
async def batch_import_todos(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    return {"code": 200, "message": "success", "data": {"imported": 0, "skipped": 0}}


@router.get("/review-pending")
async def get_review_pending(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Todo).where(Todo.review_status == "pending").order_by(Todo.created_at.desc())
    )
    items = result.scalars().all()
    return {"code": 200, "message": "success", "data": [TodoResponse.model_validate(i) for i in items]}


@router.patch("/review/{todo_id}/confirm")
async def confirm_review(
    todo_id: str,
    payload: TodoReviewConfirm | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    todo = await _get_todo_or_404(todo_id, db, current_user)
    todo.review_status = "confirmed"
    todo.review_reason = None
    if payload:
        data = _normalize_todo_time_fields(payload.model_dump(exclude_unset=True))
        for k, v in data.items():
            setattr(todo, k, v)
    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.patch("/review/{todo_id}/reject")
async def reject_review(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    todo = await _get_todo_or_404(todo_id, db, current_user)
    todo.review_status = "rejected"
    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.post("/review/batch-confirm")
async def batch_confirm_review(
    body: BatchIdsBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    todo_ids = body.todo_ids
    if not getattr(current_user, "is_superuser", False):
        result = await db.execute(
            select(Todo).where(Todo.id.in_(todo_ids), Todo.creator_id == current_user.id)
        )
    else:
        result = await db.execute(select(Todo).where(Todo.id.in_(todo_ids)))
    items = result.scalars().all()
    for todo in items:
        todo.review_status = "confirmed"
    await db.flush()
    return {"code": 200, "message": "success", "data": {"confirmed": len(items)}}


@router.post("/review/batch-reject")
async def batch_reject_review(
    body: BatchIdsBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    todo_ids = body.todo_ids
    result = await db.execute(select(Todo).where(Todo.id.in_(todo_ids)))
    items = result.scalars().all()
    for todo in items:
        todo.review_status = "rejected"
    await db.flush()
    return {"code": 200, "message": "success", "data": {"rejected": len(items)}}


@router.post("/smart-discover")
async def smart_discover_todos(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        data = await todo_discovery_engine.smart_discover(db)
        if not getattr(current_user, "is_superuser", False):
            data = {**data, "scope": "current_user"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMServiceError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {
        "code": 200,
        "message": "success",
        "data": data,
    }
