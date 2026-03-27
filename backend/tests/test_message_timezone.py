from datetime import datetime

from app.schemas.message import MessageResponse


def test_message_response_created_at_serializes_to_beijing():
    response = MessageResponse(
        id="msg-1",
        type="todo_due",
        title="提醒",
        content="请处理任务",
        status="unread",
        created_at=datetime(2026, 3, 20, 0, 0, 0),
    )

    dumped = response.model_dump()

    assert dumped["created_at"] == "2026-03-20T08:00:00+08:00"

