from __future__ import annotations

import json

from app.models import Todo
from app.services.message_service import create_todo_messages_for_users
from app.utils.timezone import utc_now_naive


async def set_todo_status(
    db,
    *,
    todo: Todo,
    new_status: str,
    operator_user_id: str | None,
    reason: str | None = None,
    failure_code: str | None = None,
    failure_stage: str | None = None,
    failure_detail: str | None = None,
    failure_meta: dict | None = None,
) -> Todo:
    old_status = todo.status
    if old_status == new_status:
        return todo

    todo.status = new_status
    if new_status == "completed":
        todo.completed_at = utc_now_naive()
    await db.flush()

    recipients = [todo.creator_id, todo.original_owner_id, todo.owner_id]

    if new_status == "completed":
        await create_todo_messages_for_users(
            db,
            type="task_completed",
            todo=todo,
            recipient_user_ids=recipients,
            sender_user_id=operator_user_id,
        )
    elif new_status == "failed":
        lines = [
            f"任务执行失败：{todo.title}",
            f"- todo_id: {todo.id}",
            f"- operator_user_id: {operator_user_id or 'system'}",
            f"- failure_code: {failure_code or 'UNKNOWN'}",
            f"- failure_stage: {failure_stage or 'unknown'}",
        ]
        if reason:
            lines.append(f"- reason: {reason}")
        if failure_detail:
            lines.append(f"- detail: {failure_detail}")
        if failure_meta:
            try:
                meta_str = json.dumps(failure_meta, ensure_ascii=False, default=str)
            except Exception:
                meta_str = str(failure_meta)
            lines.append(f"- meta: {meta_str}")
        content = "\n".join(lines)
        await create_todo_messages_for_users(
            db,
            type="task_failed",
            todo=todo,
            recipient_user_ids=recipients,
            sender_user_id=operator_user_id,
            content_override=content,
        )

    return todo
