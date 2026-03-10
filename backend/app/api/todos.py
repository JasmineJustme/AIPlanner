from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Todo
from pydantic import BaseModel
from app.schemas.todo import TodoCreate, TodoUpdate, TodoResponse, TodoReviewConfirm


class BatchIdsBody(BaseModel):
    todo_ids: list[str] = []


router = APIRouter(prefix="/todos", tags=["todos"])


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

    for todo in items:
        entry = get_orchestration_entry(todo.orchestration_id or "") if todo.orchestration_id else None
        if not entry:
            if todo.status != "pending_confirm" or todo.orchestration_id is not None:
                todo.status = "pending_confirm"
                todo.orchestration_id = None
                changed = True
            continue

        next_status = map_orchestration_status_to_todo_status(entry.get("status"))
        if todo.status != next_status:
            todo.status = next_status
            changed = True

    if changed:
        await db.flush()


@router.get("")
async def list_todos(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    priority: str | None = Query(None),
    source: str | None = Query(None),
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
    data = payload.model_dump()
    todo = Todo(
        title=data["title"],
        description=data.get("description"),
        status="pending",
        priority=data.get("priority", "medium"),
        source=data.get("source", "manual"),
        due_date=data.get("due_date"),
        tags=data.get("tags", []),
        project=data.get("project"),
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
    result = await db.execute(select(Todo).where(Todo.id == todo_id))
    todo = result.scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(todo, k, v)
    await db.flush()
    await db.refresh(todo)
    return {"code": 200, "message": "success", "data": TodoResponse.model_validate(todo)}


@router.delete("/{todo_id}")
async def delete_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Todo).where(Todo.id == todo_id))
    todo = result.scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
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
    result = await db.execute(select(Todo).where(Todo.id == todo_id))
    todo = result.scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
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
    result = await db.execute(select(Todo).where(Todo.id == todo_id))
    todo = result.scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
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
