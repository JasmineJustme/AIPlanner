from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, Todo
from app.services.message_service import create_todo_messages_for_users
from app.utils.timezone import utc_now_naive


async def scan_and_send_deadline_reminders(db: AsyncSession) -> dict:
    now = utc_now_naive()
    todos = (
        await db.execute(
            select(Todo).where(
                Todo.due_date.is_not(None),
                Todo.due_date <= now,
                Todo.status != "completed",
            )
        )
    ).scalars().all()

    sent = 0
    skipped = 0

    for todo in todos:
        recipients = [todo.owner_id] if todo.owner_id else []
        for recipient in recipients:
            existing = (
                await db.execute(
                    select(Message).where(
                        and_(
                            Message.type == "deadline_reminder",
                            Message.related_type == "todo",
                            Message.related_id == todo.id,
                            Message.recipient_user_id == recipient,
                            Message.created_at >= now - timedelta(days=1),
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            await create_todo_messages_for_users(
                db,
                type="deadline_reminder",
                todo=todo,
                recipient_user_ids=[recipient],
                sender_user_id=None,
            )
            sent += 1

    await db.flush()
    return {
        "scanned": len(todos),
        "sent": sent,
        "skipped": skipped,
        "at": now.isoformat(),
    }
