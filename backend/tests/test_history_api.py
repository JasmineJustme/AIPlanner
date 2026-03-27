from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import history as history_api
from app.models.base import Base
from app.models.execution import ExecutionHistory


@pytest.mark.asyncio
async def test_list_execution_history_includes_input_params():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[ExecutionHistory.__table__])

    try:
        async with session_factory() as db:
            db.add(
                ExecutionHistory(
                    id="history-1",
                    task_id="task-1",
                    agent_name="测试Agent",
                    status="completed",
                    input_params={"account": "张三", "context": "推送周报"},
                    output_result={"ok": True},
                    duration_ms=0,
                    started_at=datetime(2026, 3, 11, 16, 10, 56),
                    completed_at=datetime(2026, 3, 11, 16, 10, 56),
                )
            )
            await db.commit()

            result = await history_api.list_execution_history(page=1, size=20, status=None, agent_id=None, db=db)

        assert result["data"]["items"][0]["input_params"] == {"account": "张三", "context": "推送周报"}
        assert result["data"]["items"][0]["duration_ms"] == 0
    finally:
        await engine.dispose()
