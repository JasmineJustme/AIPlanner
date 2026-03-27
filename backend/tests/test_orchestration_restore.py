from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import orchestration as orchestration_api
from app.models.agent import Agent
from app.models.base import Base
from app.models.orchestration import Orchestration
from app.models.schedule import SchedulePlan, ScheduleTask
from app.models.todo import Todo
from app.models.wagent import WAgent

ALL_TABLES = [
    Todo.__table__,
    SchedulePlan.__table__,
    ScheduleTask.__table__,
    Orchestration.__table__,
]


@pytest.mark.asyncio
async def test_cancel_orchestration_removes_record_resets_todos_and_cancels_schedule(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=ALL_TABLES)

    broadcast_events: list[tuple[str, dict]] = []

    async def fake_broadcast(event_type: str, payload: dict):
        broadcast_events.append((event_type, payload))

    monkeypatch.setattr(orchestration_api.sse_manager, "broadcast", fake_broadcast)

    try:
        async with session_factory() as db:
            todo_1 = Todo(
                id="todo-cancel-1",
                title="任务1",
                source="manual",
                status="orchestrating",
                orchestration_id="orch-cancel-test",
            )
            todo_2 = Todo(
                id="todo-cancel-2",
                title="任务2",
                source="manual",
                status="orchestrating",
                orchestration_id="orch-cancel-test",
            )
            plan = SchedulePlan(id="plan-cancel-1", name="取消测试计划", status="active")
            task = ScheduleTask(
                id="task-cancel-1",
                plan_id=plan.id,
                orchestration_id="orch-cancel-test",
                status="pending",
                scheduled_at=datetime(2026, 3, 11, 10, 0, 0),
            )
            orch = Orchestration(
                id="orch-cancel-test",
                status="pending_confirm",
                todos_snapshot=[{"id": "todo-cancel-1"}, {"id": "todo-cancel-2"}],
            )
            db.add_all([todo_1, todo_2, plan, task, orch])
            await db.flush()

            result = await orchestration_api.cancel_orchestration("orch-cancel-test", db)
            await db.commit()

            todos = (
                await db.execute(
                    select(Todo).where(Todo.id.in_(["todo-cancel-1", "todo-cancel-2"]))
                )
            ).scalars().all()
            reloaded_task = await db.get(ScheduleTask, task.id)
            reloaded_plan = await db.get(SchedulePlan, plan.id)
            reloaded_orch = await db.get(Orchestration, "orch-cancel-test")

        assert result["data"] == {"status": "cancelled", "removed": True}
        assert reloaded_orch is None
        assert [todo.status for todo in todos] == ["pending_confirm", "pending_confirm"]
        assert [todo.orchestration_id for todo in todos] == [None, None]
        assert reloaded_task is not None
        assert reloaded_task.status == "cancelled"
        assert reloaded_task.error_message == "编排已取消"
        assert reloaded_plan is not None
        assert reloaded_plan.status == "cancelled"
        assert broadcast_events == [
            (
                "orchestration_complete",
                {"orch_id": "orch-cancel-test", "status": "cancelled", "error": None, "removed": True},
            )
        ]
    finally:
        await engine.dispose()


def test_build_orchestration_summary_prefers_title():
    summary = orchestration_api.build_orchestration_summary(
        [
            {"title": "标题A", "description": "描述A"},
            {"title": "标题B", "description": "描述B"},
        ]
    )

    assert summary == "标题A 等 2 个任务"


@pytest.mark.asyncio
async def test_retry_orchestration_allows_pending_confirm(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, Orchestration.__table__],
        )

    async def fake_orchestrate(db, todo_ids):
        return {
            "status": "pending_confirm",
            "plan": {
                "plan_type": "agent",
                "recommended_id": "agent-1",
                "recommended_name": "测试Agent",
                "reason": "重新编排成功",
                "input_params": {},
                "priority": "medium",
                "estimated_duration_minutes": 30,
                "start_time": "2026-03-10T10:00:00",
                "deadline": "2026-03-10T10:30:00",
                "steps": [],
            },
            "llm_reason": "重新编排成功",
        }

    monkeypatch.setattr(orchestration_api.orchestrator, "orchestrate", fake_orchestrate)
    monkeypatch.setattr(orchestration_api, "_launch_analysis", lambda *a: None)

    try:
        async with session_factory() as db:
            db.add(
                Todo(
                    id="todo-retry-1",
                    title="需要重新编排的任务",
                    source="manual",
                    status="orchestrating",
                    orchestration_id="orch-retry-1",
                )
            )
            db.add(
                Orchestration(
                    id="orch-retry-1",
                    status="pending_confirm",
                    todos_snapshot=[{"id": "todo-retry-1", "title": "需要重新编排的任务"}],
                    plan={"plan_type": "agent", "recommended_id": "old-agent"},
                    llm_reason="旧原因",
                    suggested_agent={"id": "old-agent", "name": "旧Agent", "is_enabled": True},
                )
            )
            await db.commit()

            result = await orchestration_api.retry_orchestration("orch-retry-1", db)
            assert result["data"]["status"] == "analyzing"

            event_status, _ = await orchestration_api._process_analysis(
                db, "orch-retry-1", ["todo-retry-1"], {}
            )
            await db.commit()

            orch = await db.get(Orchestration, "orch-retry-1")

        assert event_status == "pending_confirm"
        assert orch.plan["recommended_id"] == "agent-1"
        assert orch.llm_reason == "重新编排成功"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_orchestration_keeps_plan_start_time_aligned_with_scheduled_at(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=ALL_TABLES)

    try:
        async with session_factory() as db:
            db.add(
                Todo(
                    id="todo-time-1",
                    title="时间对齐任务",
                    source="manual",
                    status="orchestrating",
                    orchestration_id="orch-time-1",
                )
            )
            db.add(
                Orchestration(
                    id="orch-time-1",
                    summary="时间对齐任务",
                    status="pending_confirm",
                    todos_snapshot=[{"id": "todo-time-1", "title": "时间对齐任务"}],
                    plan={
                        "plan_type": "agent",
                        "recommended_id": "",
                        "recommended_name": "",
                        "input_params": {},
                        "priority": "medium",
                        "start_time": None,
                        "deadline": None,
                    },
                )
            )
            await db.commit()

            await orchestration_api.confirm_orchestration(
                "orch-time-1",
                payload={
                    "start_time": "2026-03-10T02:00:00.000Z",
                    "deadline": "2026-03-10T03:00:00.000Z",
                },
                db=db,
            )
            await db.commit()

            task = (await db.execute(select(ScheduleTask))).scalar_one()
            orch = await db.get(Orchestration, "orch-time-1")

        assert orch.plan["start_time"] == task.scheduled_at.isoformat()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_pending_orchestrations_excludes_cancelled_entries():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[Orchestration.__table__]
        )

    try:
        async with session_factory() as db:
            db.add(
                Orchestration(
                    id="orch-active",
                    status="pending_confirm",
                    submitted_at=datetime(2026, 3, 11, 10, 0, 0),
                    todos_snapshot=[{"id": "todo-1", "title": "保留任务"}],
                )
            )
            db.add(
                Orchestration(
                    id="orch-cancelled",
                    status="cancelled",
                    submitted_at=datetime(2026, 3, 11, 9, 0, 0),
                    todos_snapshot=[{"id": "todo-2", "title": "取消任务"}],
                )
            )
            await db.commit()

            result = await orchestration_api.list_pending_orchestrations(db=db)

        assert [item["orch_id"] for item in result["data"]] == ["orch-active"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_modify_agent_updates_selected_executor_and_keeps_llm_recommendation(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Agent.__table__, WAgent.__table__, Orchestration.__table__],
        )

    try:
        async with session_factory() as db:
            db.add_all(
                [
                    Agent(
                        id="agent-llm-1",
                        name="LLM推荐Agent",
                        dify_endpoint="https://example.com/agent-llm",
                        dify_api_key="secret-1",
                        input_params=[
                            {"name": "contact", "default": ""},
                            {"name": "message", "default": ""},
                        ],
                        output_params={},
                        is_enabled=True,
                    ),
                    Agent(
                        id="agent-user-1",
                        name="用户改选Agent",
                        dify_endpoint="https://example.com/agent-user",
                        dify_api_key="secret-2",
                        input_params=[
                            {"name": "contact", "default": "默认联系人"},
                            {"name": "message", "default": "默认消息"},
                        ],
                        output_params={},
                        is_enabled=True,
                    ),
                ]
            )
            db.add(
                Orchestration(
                    id="orch-modify-1",
                    status="pending_confirm",
                    todos_snapshot=[{"id": "todo-1", "title": "测试任务"}],
                    plan={
                        "plan_type": "agent",
                        "recommended_id": "agent-llm-1",
                        "recommended_name": "LLM推荐Agent",
                        "reason": "LLM 推荐理由",
                        "input_params": {"contact": "全行室经理", "message": "本周工作报告总结"},
                    },
                    suggested_agent={"id": "agent-llm-1", "name": "LLM推荐Agent", "is_enabled": True, "type": "agent"},
                    llm_reason="LLM 推荐理由",
                )
            )
            await db.commit()

            result = await orchestration_api.modify_agent(
                "orch-modify-1",
                {"plan_type": "agent", "recommended_id": "agent-user-1"},
                db,
            )

            restored = await orchestration_api.modify_agent(
                "orch-modify-1",
                {"plan_type": "agent", "recommended_id": "agent-llm-1"},
                db,
            )

        updated = result["data"]
        assert updated["plan"]["recommended_id"] == "agent-user-1"
        assert updated["plan"]["recommended_name"] == "用户改选Agent"
        assert updated["suggested_agent"]["id"] == "agent-user-1"
        assert updated["suggested_agent"]["name"] == "用户改选Agent"
        assert updated["suggested_wagent"] is None
        assert updated["llm_recommended_id"] == "agent-llm-1"
        assert updated["llm_recommended_name"] == "LLM推荐Agent"
        assert updated["llm_recommended_type"] == "agent"
        assert updated["plan"]["input_params"] == {"contact": "默认联系人", "message": "默认消息"}
        assert restored["data"]["plan"]["input_params"] == {"contact": "全行室经理", "message": "本周工作报告总结"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_retry_orchestration_error_keeps_analyzing_status_and_broadcasts_failed(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, Orchestration.__table__],
        )

    async def fake_orchestrate(_db, _todo_ids):
        return {"error": "retry llm failure"}

    monkeypatch.setattr(orchestration_api.orchestrator, "orchestrate", fake_orchestrate)
    monkeypatch.setattr(orchestration_api, "_launch_analysis", lambda *a: None)

    try:
        async with session_factory() as db:
            db.add(
                Todo(
                    id="todo-retry-failed-1",
                    title="重试失败任务",
                    source="manual",
                    status="orchestrating",
                    orchestration_id="orch-retry-failed-1",
                )
            )
            db.add(
                Orchestration(
                    id="orch-retry-failed-1",
                    status="pending_confirm",
                    todos_snapshot=[{"id": "todo-retry-failed-1", "title": "重试失败任务"}],
                    plan={"plan_type": "agent", "recommended_id": "old-agent"},
                    llm_reason="旧原因",
                    suggested_agent={"id": "old-agent", "name": "旧Agent", "is_enabled": True},
                )
            )
            await db.commit()

            result = await orchestration_api.retry_orchestration("orch-retry-failed-1", db)
            assert result["data"]["status"] == "analyzing"

            event_status, error_msg = await orchestration_api._process_analysis(
                db, "orch-retry-failed-1", ["todo-retry-failed-1"], {}
            )
            await db.flush()

            reloaded = await db.get(Todo, "todo-retry-failed-1")
            orch = await db.get(Orchestration, "orch-retry-failed-1")

        assert event_status == "pending_confirm"
        assert error_msg == "retry llm failure"
        assert orch.status == "pending_confirm"
        assert reloaded is not None
        assert reloaded.status == "orchestrating"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_process_analysis_llm_timeout_uses_fallback_plan_and_keeps_pending_confirm(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, Orchestration.__table__],
        )

    async def fake_orchestrate(_db, _todo_ids):
        return {
            "status": "pending_confirm",
            "plan": {
                "plan_type": "agent",
                "recommended_id": "agent-fallback-1",
                "recommended_name": "兜底Agent",
                "reason": "LLM 超时，使用兜底方案",
                "input_params": {"topic": "默认参数"},
                "priority": "medium",
                "estimated_duration_minutes": 30,
                "start_time": "2026-03-10T10:00:00",
                "deadline": "2026-03-10T10:30:00",
                "steps": [],
            },
            "llm_reason": "[LLM 调用失败，已自动回退] LLM 超时，使用兜底方案",
            "llm_error": "ReadTimeout",
        }

    monkeypatch.setattr(orchestration_api.orchestrator, "orchestrate", fake_orchestrate)

    try:
        async with session_factory() as db:
            db.add(
                Todo(
                    id="todo-fallback-1",
                    title="超时兜底任务",
                    source="manual",
                    status="orchestrating",
                    orchestration_id="orch-fallback-1",
                )
            )
            db.add(
                Orchestration(
                    id="orch-fallback-1",
                    status="analyzing",
                    todos_snapshot=[{"id": "todo-fallback-1", "title": "超时兜底任务"}],
                )
            )
            await db.commit()

            event_status, error_msg = await orchestration_api._process_analysis(
                db, "orch-fallback-1", ["todo-fallback-1"], {}
            )
            await db.flush()

            orch = await db.get(Orchestration, "orch-fallback-1")
            todo = await db.get(Todo, "todo-fallback-1")

        assert event_status == "pending_confirm"
        assert error_msg is not None
        assert "LLM 未返回有效结果" in error_msg
        assert "ReadTimeout" in error_msg
        assert orch is not None
        assert orch.status == "pending_confirm"
        assert orch.plan is not None
        assert orch.plan.get("recommended_id") == "agent-fallback-1"
        assert orch.error == error_msg
        assert todo is not None
        assert todo.status == "orchestrating"
    finally:
        await engine.dispose()
