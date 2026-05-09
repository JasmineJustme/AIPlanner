from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, Todo
from app.services.sse_manager import sse_manager


SYSTEM_MESSAGE_TYPES = {
    "review_new",
    "task_completed",
    "task_failed",
    "deadline_reminder",
    "system",
}


def _normalize_recipient_ids(recipient_user_ids: list[str | None]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in recipient_user_ids:
        user_id = str(item or "").strip()
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        normalized.append(user_id)
    return normalized


async def create_system_message(
    db: AsyncSession,
    *,
    type: str,
    title: str,
    content: str,
    related_type: str | None = None,
    related_id: str | None = None,
    recipient_user_id: str | None = None,
    sender_user_id: str | None = None,
    related_request_id: str | None = None,
    action_url: str | None = None,
    dedup_key: str | None = None,
    dedup_since: datetime | None = None,
) -> Message:
    if type not in SYSTEM_MESSAGE_TYPES and not type.startswith("system_"):
        # keep it flexible for future types while still explicit for known set
        pass

    if dedup_key and dedup_since:
        existing = (
            await db.execute(
                select(Message).where(
                    and_(
                        Message.type == type,
                        Message.related_type == related_type,
                        Message.related_id == related_id,
                        Message.recipient_user_id == recipient_user_id,
                        Message.created_at >= dedup_since,
                        Message.content == dedup_key,
                    )
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

    msg = Message(
        type=type,
        title=title,
        content=content,
        status="unread",
        related_type=related_type,
        related_id=related_id,
        related_request_id=related_request_id,
        recipient_user_id=recipient_user_id,
        sender_user_id=sender_user_id,
        action_url=action_url,
    )
    db.add(msg)
    await db.flush()

    try:
        await sse_manager.broadcast(
            "message",
            {
                "type": type,
                "message_id": msg.id,
                "recipient_user_id": recipient_user_id,
                "related_type": related_type,
                "related_id": related_id,
            },
        )
        await sse_manager.broadcast(
            type,
            {
                "message_id": msg.id,
                "recipient_user_id": recipient_user_id,
                "related_type": related_type,
                "related_id": related_id,
            },
        )
    except Exception:
        # SSE 推送失败不应影响消息落库
        pass

    return msg


async def create_todo_system_message(
    db: AsyncSession,
    *,
    type: str,
    todo: Todo,
    recipient_user_id: str | None,
    sender_user_id: str | None = None,
    content_override: str | None = None,
    title_override: str | None = None,
) -> Message:
    title = title_override or todo.title
    default_content_map = {
        "review_new": f"智能发掘产生新待办，请及时审核：{todo.title}",
        "task_completed": f"任务已完成：{todo.title}",
        "task_failed": f"任务执行失败：{todo.title}",
        "deadline_reminder": f"任务已到截止时间但尚未完成：{todo.title}",
    }
    content = content_override or default_content_map.get(type, todo.title)
    return await create_system_message(
        db,
        type=type,
        title=title,
        content=content,
        related_type="todo",
        related_id=todo.id,
        recipient_user_id=recipient_user_id,
        sender_user_id=sender_user_id,
        related_request_id=None,
        action_url=None,
    )


async def create_todo_messages_for_users(
    db: AsyncSession,
    *,
    type: str,
    todo: Todo,
    recipient_user_ids: list[str | None],
    sender_user_id: str | None = None,
    content_override: str | None = None,
    title_override: str | None = None,
) -> list[Message]:
    recipients = _normalize_recipient_ids(recipient_user_ids)
    items: list[Message] = []
    for recipient in recipients:
        item = await create_todo_system_message(
            db,
            type=type,
            todo=todo,
            recipient_user_id=recipient,
            sender_user_id=sender_user_id,
            content_override=content_override,
            title_override=title_override,
        )
        items.append(item)
    return items


async def count_due_todos(
    db: AsyncSession,
    *,
    now: datetime,
) -> int:
    result = await db.execute(
        select(func.count()).select_from(Todo).where(Todo.due_date.is_not(None), Todo.due_date <= now, Todo.status != "completed")
    )
    return result.scalar() or 0
