from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.todo_discovery import todo_discovery_engine
from app.models import Todo, ScheduleTask
from app.services.llm_client import LLMServiceError
from pydantic import BaseModel
from app.schemas.todo import TodoCreate, TodoUpdate, TodoResponse, TodoReviewConfirm


class BatchIdsBody(BaseModel):
    todo_ids: list[str] = []


router = APIRouter(prefix="/todos", tags=["todos"])


def _normalize_recurrence_fields(data: dict) -> dict:
    is_recurring = bool(data.get("is_recurring", False))
    normalized = dict(data)
    normalized["is_recurring"] = is_recurring
    if not is_recurring:
        normalized["recurrence_cron"] = None
        normalized["recurrence_count"] = 0
    else:
        normalized["recurrence_count"] = int(data.get("recurrence_count") or 0)
    return normalized


async def _reconcile_orchestration_todo_statuses(db: AsyncSession) -> None:
    from app.api.orchestration import get_orchestration_entry, map_orchestration_status_to_todo_status

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
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)

    orchestration_ids = [todo.orchestration_id for todo in items if todo.orchestration_id]
    latest_completion_by_orch: dict[str, datetime] = {}
    if orchestration_ids:
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

    for todo in items:
        entry = get_orchestration_entry(todo.orchestration_id or "") if todo.orchestration_id else None
        if not entry:
            if todo.status != "pending_confirm" or todo.orchestration_id is not None or todo.completed_at is not None:
                todo.status = "pending_confirm"
                todo.orchestration_id = None
                todo.completed_at = None
                changed = True
            continue

        next_status = map_orchestration_status_to_todo_status(entry.get("status"))
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


async def _get_todo_or_404(todo_id: str, db: AsyncSession) -> Todo:
    result = await db.execute(select(Todo).where(Todo.id == todo_id))
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
):
    await _reconcile_orchestration_todo_statuses(db)
    offset = (page - 1) * size
    q = select(Todo)
    count_q = select(func.count()).select_from(Todo)
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
):
    data = _normalize_recurrence_fields(payload.model_dump())
    todo = Todo(
        title=data["title"],
        description=data.get("description"),
        status="pending",
        priority=data.get("priority", "medium"),
        source=data.get("source", "manual"),
        execution_mode=data.get("execution_mode", "system"),
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
):
    todo = await _get_todo_or_404(todo_id, db)
    data = payload.model_dump(exclude_unset=True)

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
):
    todo = await _get_todo_or_404(todo_id, db)
    if todo.execution_mode != "user":
        raise HTTPException(status_code=400, detail="仅用户执行任务支持手动完成")
    if todo.status not in {"pending", "pending_confirm"}:
        raise HTTPException(status_code=400, detail="仅待确认的用户执行任务支持手动完成")

    todo.status = "completed"
    todo.completed_at = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    todo.orchestration_id = None
    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.patch("/{todo_id}/confirm")
async def confirm_user_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
):
    todo = await _get_todo_or_404(todo_id, db)
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
):
    todo = await _get_todo_or_404(todo_id, db)
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
):
    todo = await _get_todo_or_404(todo_id, db)
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
):
    todo = await _get_todo_or_404(todo_id, db)
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
):
    todo = await _get_todo_or_404(todo_id, db)
    todo.review_status = "confirmed"
    todo.review_reason = None
    if payload:
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(todo, k, v)
    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.patch("/review/{todo_id}/reject")
async def reject_review(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
):
    todo = await _get_todo_or_404(todo_id, db)
    todo.review_status = "rejected"
    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.post("/review/batch-confirm")
async def batch_confirm_review(
    body: BatchIdsBody,
    db: AsyncSession = Depends(get_db),
):
    todo_ids = body.todo_ids
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
):
    try:
        data = await todo_discovery_engine.smart_discover(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMServiceError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {
        "code": 200,
        "message": "success",
        "data": data,
    }
