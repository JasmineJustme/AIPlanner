from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import Message, Todo
from pydantic import BaseModel
from app.schemas.message import MessageResponse
from app.utils.timezone import beijing_to_utc_naive


class BatchMessageIdsBody(BaseModel):
    message_ids: list[str] = []


router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("")
async def list_messages(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    type: str | None = Query(None, alias="type"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    offset = (page - 1) * size
    q = select(Message)
    count_q = select(func.count()).select_from(Message)
    if not getattr(current_user, "is_superuser", False):
        q = q.where(Message.recipient_user_id == current_user.id)
        count_q = count_q.where(Message.recipient_user_id == current_user.id)
    q = q.outerjoin(Todo, and_(Message.related_type == "todo", Message.related_id == Todo.id))
    count_q = count_q.outerjoin(Todo, and_(Message.related_type == "todo", Message.related_id == Todo.id))
    exclude_flow_completed = and_(
        Message.type == "task_completed",
        Message.related_type == "todo",
        Todo.last_flow_type.in_(["dispatch", "collaboration", "collaboration_accept"]),
    )
    q = q.where(not_(exclude_flow_completed))
    count_q = count_q.where(not_(exclude_flow_completed))
    if status:
        q = q.where(Message.status == status)
        count_q = count_q.where(Message.status == status)
    if type:
        q = q.where(Message.type == type)
        count_q = count_q.where(Message.type == type)
    if start_date:
        start_dt = beijing_to_utc_naive(datetime.strptime(start_date, "%Y-%m-%d"))
        q = q.where(Message.created_at >= start_dt)
        count_q = count_q.where(Message.created_at >= start_dt)
    if end_date:
        end_dt = beijing_to_utc_naive(datetime.strptime(end_date + " 23:59:59", "%Y-%m-%d %H:%M:%S"))
        q = q.where(Message.created_at <= end_dt)
        count_q = count_q.where(Message.created_at <= end_dt)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0
    result = await db.execute(q.offset(offset).limit(size).order_by(Message.created_at.desc()))
    items = result.scalars().all()
    pages = (total + size - 1) // size if total > 0 else 0
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [MessageResponse.model_validate(i) for i in items],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        },
    }


@router.get("/unread-count")
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(func.count()).select_from(Message).where(Message.status == "unread")
    if not getattr(current_user, "is_superuser", False):
        q = q.where(Message.recipient_user_id == current_user.id)
    result = await db.execute(q)
    count = result.scalar() or 0
    return {"code": 200, "message": "success", "data": {"count": count}}


@router.patch("/{message_id}/read")
async def mark_read(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(Message).where(Message.id == message_id)
    if not getattr(current_user, "is_superuser", False):
        q = q.where(Message.recipient_user_id == current_user.id)
    result = await db.execute(q)
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.status = "read"
    await db.flush()
    await db.refresh(msg)
    return {"code": 200, "message": "success", "data": MessageResponse.model_validate(msg)}


@router.patch("/{message_id}/processed")
async def mark_processed(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(Message).where(Message.id == message_id)
    if not getattr(current_user, "is_superuser", False):
        todo_ids_q = select(Todo.id).where(or_(Todo.creator_id == current_user.id, Todo.original_owner_id == current_user.id, Todo.owner_id == current_user.id))
        q = q.where(or_(Message.recipient_user_id == current_user.id, Message.related_type != "todo", Message.related_id.in_(todo_ids_q)))
    result = await db.execute(q)
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.status = "processed"
    await db.flush()
    await db.refresh(msg)
    return {"code": 200, "message": "success", "data": MessageResponse.model_validate(msg)}


@router.post("/batch-read")
async def batch_read(
    body: BatchMessageIdsBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    message_ids = body.message_ids
    q = select(Message).where(Message.id.in_(message_ids))
    if not getattr(current_user, "is_superuser", False):
        todo_ids_q = select(Todo.id).where(or_(Todo.creator_id == current_user.id, Todo.original_owner_id == current_user.id, Todo.owner_id == current_user.id))
        q = q.where(or_(Message.recipient_user_id == current_user.id, Message.related_type != "todo", Message.related_id.in_(todo_ids_q)))
    result = await db.execute(q)
    items = result.scalars().all()
    for msg in items:
        msg.status = "read"
    await db.flush()
    return {"code": 200, "message": "success", "data": {"updated": len(items)}}


@router.delete("/batch-delete")
async def batch_delete(
    body: BatchMessageIdsBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    message_ids = body.message_ids
    q = select(Message).where(Message.id.in_(message_ids))
    if not getattr(current_user, "is_superuser", False):
        todo_ids_q = select(Todo.id).where(or_(Todo.creator_id == current_user.id, Todo.original_owner_id == current_user.id, Todo.owner_id == current_user.id))
        q = q.where(or_(Message.recipient_user_id == current_user.id, Message.related_type != "todo", Message.related_id.in_(todo_ids_q)))
    result = await db.execute(q)
    items = result.scalars().all()
    for msg in items:
        await db.delete(msg)
    return {"code": 200, "message": "success", "data": {"deleted": len(items)}}
