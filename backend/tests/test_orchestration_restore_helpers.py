from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import orchestration as orchestration_api
from app.api.scheduling import cancel_plan, cancel_task, delay_task, get_gantt_data, list_schedule_tasks
from app.api.todos import list_todos
from app.models.agent import Agent
from app.models.base import Base
from app.models.orchestration import Orchestration
from app.models.schedule import SchedulePlan, ScheduleTask
from app.models.settings import SystemSetting
from app.models.todo import Todo

ALL_TABLES = [
    Todo.__table__,
    SchedulePlan.__table__,
    ScheduleTask.__table__,
    Orchestration.__table__,
]


@pytest.mark.asyncio
async def test_scheduling_queries_hide_cancelled_tasks_by_default():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, SchedulePlan.__table__, ScheduleTask.__table__],
        )

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-1", name="测试计划", status="active")
            db.add(plan)
            await db.flush()

            db.add_all(
                [
                    ScheduleTask(
                        id="task-visible",
                        plan_id=plan.id,
                        orchestration_id="orch-1",
                        status="pending",
                        scheduled_at=datetime(2026, 3, 9, 10, 0, 0),
                    ),
                    ScheduleTask(
                        id="task-hidden",
                        plan_id=plan.id,
                        orchestration_id="orch-1",
                        status="cancelled",
                        scheduled_at=datetime(2026, 3, 9, 11, 0, 0),
                    ),
                ]
            )
            await db.commit()

            list_result = await list_schedule_tasks(db=db)
            gantt_result = await get_gantt_data(db=db)
            cancelled_result = await list_schedule_tasks(status="cancelled", db=db)

        assert [task["id"] for task in list_result["data"]] == ["task-visible"]
        assert [task["id"] for task in gantt_result["data"]["tasks"]] == ["task-visible"]
        assert [task["id"] for task in cancelled_result["data"]] == ["task-hidden"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_todos_repairs_orphaned_orchestrating_status():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, Orchestration.__table__],
        )

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-orphan-1",
                title="孤儿编排任务",
                source="manual",
                status="orchestrating",
                orchestration_id="orch-missing-1",
            )
            db.add(todo)
            await db.commit()

            result = await list_todos(
                page=1,
                size=20,
                status=None,
                priority=None,
                source=None,
                execution_mode=None,
                db=db,
            )
            items = result["data"]["items"]

            assert len(items) == 1
            assert items[0].status == "pending_confirm"
            assert items[0].orchestration_id is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_todos_repairs_pending_confirm_with_orchestration_to_orchestrating():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, Orchestration.__table__],
        )

    try:
        async with session_factory() as db:
            db.add(
                Orchestration(
                    id="orch-pending-1",
                    status="pending_confirm",
                    todos_snapshot=[{"id": "todo-linked-1"}],
                )
            )
            todo = Todo(
                id="todo-linked-1",
                title="已提交编排任务",
                source="manual",
                status="pending_confirm",
                orchestration_id="orch-pending-1",
            )
            db.add(todo)
            await db.commit()

            result = await list_todos(
                page=1,
                size=20,
                status=None,
                priority=None,
                source=None,
                execution_mode=None,
                db=db,
            )
            items = result["data"]["items"]

            assert len(items) == 1
            assert items[0].status == "orchestrating"
            assert items[0].orchestration_id == "orch-pending-1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_orchestration_creates_schedule_records():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[*ALL_TABLES, Agent.__table__],
        )

    try:
        async with session_factory() as db:
            db.add(
                Agent(
                    id="agent-123",
                    name="跟进Agent",
                    dify_endpoint="https://example.com",
                    dify_api_key="secret",
                    input_params={},
                    output_params={},
                )
            )
            db.add(
                Todo(
                    id="todo-confirm-1",
                    title="跟进客户周报",
                    source="manual",
                    status="orchestrating",
                    orchestration_id="orch-confirm-1",
                )
            )
            db.add(
                Orchestration(
                    id="orch-confirm-1",
                    summary="跟进客户周报",
                    status="pending_confirm",
                    todos_snapshot=[{"id": "todo-confirm-1", "title": "跟进客户周报"}],
                    plan={
                        "plan_type": "agent",
                        "recommended_id": "agent-123",
                        "recommended_name": "跟进Agent",
                        "input_params": {"topic": "周报"},
                        "priority": "high",
                        "start_time": "2026-03-10T10:00:00",
                        "deadline": "2026-03-10T11:00:00",
                    },
                )
            )
            await db.commit()

            result = await orchestration_api.confirm_orchestration("orch-confirm-1", db=db)
            await db.commit()

            plans = (await db.execute(select(SchedulePlan))).scalars().all()
            tasks = (await db.execute(select(ScheduleTask))).scalars().all()
            scheduling_result = await list_schedule_tasks(db=db)

        assert result["data"]["status"] == "confirmed"
        assert len(plans) == 1
        assert plans[0].name == "跟进客户周报"
        assert len(tasks) == 1
        assert tasks[0].orchestration_id == "orch-confirm-1"
        assert tasks[0].agent_id == "agent-123"
        assert tasks[0].status == "pending"
        assert tasks[0].priority == "high"
        assert tasks[0].scheduled_at.isoformat() == "2026-03-10T10:00:00"
        assert len(scheduling_result["data"]) == 1
        assert scheduling_result["data"][0]["orchestration_id"] == "orch-confirm-1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_orchestration_after_cancelled_history_creates_new_plan():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[*ALL_TABLES, Agent.__table__],
        )

    try:
        async with session_factory() as db:
            db.add(
                Agent(
                    id="agent-321",
                    name="重提Agent",
                    dify_endpoint="https://example.com",
                    dify_api_key="secret",
                    input_params={},
                    output_params={},
                )
            )

            old_plan = SchedulePlan(id="plan-old-cancelled", name="旧计划", status="cancelled")
            old_task = ScheduleTask(
                id="task-old-cancelled",
                plan_id=old_plan.id,
                orchestration_id="orch-confirm-reopen-1",
                agent_id="agent-321",
                status="cancelled",
                priority="medium",
                scheduled_at=datetime(2026, 3, 10, 9, 0, 0),
                input_params={"topic": "旧参数"},
            )
            db.add_all(
                [
                    old_plan,
                    old_task,
                    Todo(
                        id="todo-confirm-reopen-1",
                        title="取消后重提任务",
                        source="manual",
                        status="orchestrating",
                        orchestration_id="orch-confirm-reopen-1",
                    ),
                    Orchestration(
                        id="orch-confirm-reopen-1",
                        summary="取消后重提任务",
                        status="pending_confirm",
                        todos_snapshot=[{"id": "todo-confirm-reopen-1", "title": "取消后重提任务"}],
                        plan={
                            "plan_type": "agent",
                            "recommended_id": "agent-321",
                            "recommended_name": "重提Agent",
                            "input_params": {"topic": "新参数"},
                            "priority": "medium",
                            "start_time": "2026-03-11T10:00:00",
                            "deadline": "2026-03-11T11:00:00",
                        },
                    ),
                ]
            )
            await db.commit()

            await orchestration_api.confirm_orchestration("orch-confirm-reopen-1", db=db)
            await db.commit()

            all_plans = (await db.execute(select(SchedulePlan))).scalars().all()
            all_tasks = (await db.execute(select(ScheduleTask))).scalars().all()
            new_tasks = [t for t in all_tasks if t.id != "task-old-cancelled"]

        assert len(all_plans) == 2
        assert len(new_tasks) == 1
        assert new_tasks[0].plan_id != "plan-old-cancelled"
        assert new_tasks[0].status == "pending"
        assert new_tasks[0].input_params == {"topic": "新参数"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_orchestration_error_keeps_status_pending_confirm(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[*ALL_TABLES, Agent.__table__],
        )

    async def fake_ensure(*_args, **_kwargs):
        raise HTTPException(status_code=400, detail="请勿重复提交")

    monkeypatch.setattr(orchestration_api, "ensure_schedule_for_orchestration", fake_ensure)

    try:
        async with session_factory() as db:
            db.add(
                Agent(
                    id="agent-321",
                    name="测试Agent",
                    dify_endpoint="https://example.com",
                    dify_api_key="secret",
                    input_params={},
                    output_params={},
                )
            )
            db.add(
                Todo(
                    id="todo-confirm-fail-1",
                    title="确认失败保持可见",
                    source="manual",
                    status="orchestrating",
                    orchestration_id="orch-confirm-fail-1",
                )
            )
            db.add(
                Orchestration(
                    id="orch-confirm-fail-1",
                    summary="确认失败保持可见",
                    status="pending_confirm",
                    todos_snapshot=[{"id": "todo-confirm-fail-1", "title": "确认失败保持可见"}],
                    plan={
                        "plan_type": "agent",
                        "recommended_id": "agent-321",
                        "recommended_name": "测试Agent",
                        "input_params": {},
                        "priority": "medium",
                        "start_time": "2026-03-11T10:00:00",
                        "deadline": "2026-03-11T11:00:00",
                    },
                )
            )
            await db.commit()

            with pytest.raises(HTTPException) as exc:
                await orchestration_api.confirm_orchestration("orch-confirm-fail-1", db=db)

            orch = await db.get(Orchestration, "orch-confirm-fail-1")

        assert exc.value.status_code == 400
        assert exc.value.detail == "请勿重复提交"
        assert orch.status == "pending_confirm"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_plan_deletes_schedule_records_and_resets_linked_orchestration():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=ALL_TABLES)

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-delete-1", name="待删除计划", status="active")
            task = ScheduleTask(
                id="task-delete-1",
                plan_id=plan.id,
                orchestration_id="orch-plan-cancel-1",
                status="pending",
                scheduled_at=datetime(2026, 3, 10, 10, 0, 0),
            )
            todo = Todo(
                id="todo-plan-cancel-1",
                title="取消计划测试",
                source="manual",
                status="scheduling",
                orchestration_id="orch-plan-cancel-1",
            )
            orch = Orchestration(
                id="orch-plan-cancel-1",
                summary="取消计划测试",
                status="confirmed",
                todos_snapshot=[{"id": "todo-plan-cancel-1", "title": "取消计划测试"}],
                plan={
                    "plan_type": "agent",
                    "recommended_id": "agent-1",
                    "recommended_name": "测试Agent",
                    "input_params": {},
                    "priority": "medium",
                    "start_time": "2026-03-10T10:00:00",
                    "deadline": "2026-03-10T11:00:00",
                },
            )
            db.add_all([plan, task, todo, orch])
            await db.commit()

            result = await cancel_plan("plan-delete-1", db=db)
            await db.commit()

            plans = (await db.execute(select(SchedulePlan))).scalars().all()
            tasks = (await db.execute(select(ScheduleTask))).scalars().all()
            reloaded_todo = await db.get(Todo, "todo-plan-cancel-1")
            reloaded_orch = await db.get(Orchestration, "orch-plan-cancel-1")

        assert result["data"] == {"status": "cancelled", "removed": True}
        assert plans == []
        assert tasks == []
        assert reloaded_orch.status == "pending_confirm"
        assert reloaded_todo is not None
        assert reloaded_todo.status == "orchestrating"
        assert reloaded_todo.orchestration_id == "orch-plan-cancel-1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_task_syncs_linked_orchestration_back_to_pending_confirm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=ALL_TABLES)

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-task-cancel-1", name="任务取消计划", status="active")
            task = ScheduleTask(
                id="task-cancel-sync-1",
                plan_id=plan.id,
                orchestration_id="orch-task-cancel-1",
                status="pending",
                scheduled_at=datetime(2026, 3, 10, 10, 0, 0),
            )
            todo = Todo(
                id="todo-task-cancel-1",
                title="取消任务回编排",
                source="manual",
                status="scheduling",
                orchestration_id="orch-task-cancel-1",
            )
            orch = Orchestration(
                id="orch-task-cancel-1",
                summary="取消任务回编排",
                status="confirmed",
                todos_snapshot=[{"id": "todo-task-cancel-1", "title": "取消任务回编排"}],
                plan={
                    "plan_type": "agent",
                    "recommended_id": "agent-1",
                    "recommended_name": "测试Agent",
                    "input_params": {},
                    "priority": "medium",
                    "start_time": "2026-03-10T10:00:00",
                    "deadline": "2026-03-10T11:00:00",
                },
            )
            db.add_all([plan, task, todo, orch])
            await db.commit()

            result = await cancel_task("task-cancel-sync-1", db=db)
            await db.commit()

            reloaded_task = await db.get(ScheduleTask, "task-cancel-sync-1")
            reloaded_todo = await db.get(Todo, "todo-task-cancel-1")
            reloaded_orch = await db.get(Orchestration, "orch-task-cancel-1")

        assert result["data"]["status"] == "cancelled"
        assert reloaded_task is not None
        assert reloaded_task.status == "cancelled"
        assert reloaded_orch.status == "pending_confirm"
        assert reloaded_todo is not None
        assert reloaded_todo.status == "orchestrating"
        assert reloaded_todo.orchestration_id == "orch-task-cancel-1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_modify_agent_rebuilds_input_params_and_confirm_sends_to_schedule_task():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[*ALL_TABLES, Agent.__table__],
        )

    try:
        async with session_factory() as db:
            db.add(
                Agent(
                    id="agent-new",
                    name="消息Agent",
                    dify_endpoint="https://example.com",
                    dify_api_key="secret",
                    input_params=[
                        {"name": "contact", "default": "全行室经理"},
                        {"name": "message"},
                    ],
                    output_params={},
                )
            )
            db.add(
                Todo(
                    id="todo-mod-agent-1",
                    title="发送周报",
                    source="manual",
                    status="orchestrating",
                    orchestration_id="orch-mod-agent-1",
                )
            )
            db.add(
                Orchestration(
                    id="orch-mod-agent-1",
                    summary="发送周报",
                    status="pending_confirm",
                    todos_snapshot=[{"id": "todo-mod-agent-1", "title": "发送周报"}],
                    plan={
                        "plan_type": "agent",
                        "recommended_id": "agent-old",
                        "recommended_name": "旧Agent",
                        "input_params": {"legacy": "value"},
                        "start_time": "2026-03-10T10:00:00",
                        "deadline": "2026-03-10T11:00:00",
                        "priority": "medium",
                    },
                )
            )
            await db.commit()

            modified = await orchestration_api.modify_agent(
                "orch-mod-agent-1",
                {"plan_type": "agent", "recommended_id": "agent-new"},
                db=db,
            )
            modified_plan = modified["data"]["plan"]

            assert modified_plan["recommended_id"] == "agent-new"
            assert modified_plan["input_params"] == {"contact": "全行室经理", "message": ""}
            assert modified_plan["editable_input_keys"] == ["contact", "message"]

            await orchestration_api.confirm_orchestration(
                "orch-mod-agent-1",
                payload={"input_params": {"contact": "张三", "message": "本周工作报告总结"}},
                db=db,
            )
            await db.commit()

            task = (await db.execute(select(ScheduleTask).where(ScheduleTask.orchestration_id == "orch-mod-agent-1"))).scalar_one()

        assert task.agent_id == "agent-new"
        assert task.input_params == {"contact": "张三", "message": "本周工作报告总结"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scheduling_queries_return_task_title_from_related_todo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, SchedulePlan.__table__, ScheduleTask.__table__],
        )

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-title-1", name="计划名称", status="active")
            task = ScheduleTask(
                id="task-title-1",
                plan_id=plan.id,
                orchestration_id="orch-title-1",
                status="pending",
                scheduled_at=datetime(2026, 3, 12, 9, 0, 0),
            )
            todo = Todo(
                id="todo-title-1",
                title="推送工作报告",
                source="manual",
                status="scheduling",
                orchestration_id="orch-title-1",
            )
            db.add_all([plan, task, todo])
            await db.commit()

            list_result = await list_schedule_tasks(db=db)
            gantt_result = await get_gantt_data(db=db)

        assert list_result["data"][0]["task_title"] == "推送工作报告"
        assert gantt_result["data"]["tasks"][0]["name"] == "推送工作报告"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delay_task_extends_existing_schedule_and_syncs_orchestration_start_time():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=ALL_TABLES)

    try:
        async with session_factory() as db:
            scheduled_at = datetime.now().replace(microsecond=0) + timedelta(hours=2)
            plan = SchedulePlan(id="plan-delay-1", name="延后计划", status="active")
            task = ScheduleTask(
                id="task-delay-1",
                plan_id=plan.id,
                orchestration_id="orch-delay-1",
                status="pending",
                scheduled_at=scheduled_at,
            )
            todo = Todo(
                id="todo-delay-1",
                title="延后任务",
                source="manual",
                status="scheduling",
                orchestration_id="orch-delay-1",
            )
            orch = Orchestration(
                id="orch-delay-1",
                status="confirmed",
                todos_snapshot=[{"id": "todo-delay-1", "title": "延后任务"}],
                plan={
                    "plan_type": "agent",
                    "recommended_id": "agent-delay-1",
                    "recommended_name": "延后Agent",
                    "start_time": scheduled_at.isoformat(),
                    "deadline": (scheduled_at + timedelta(hours=1)).isoformat(),
                },
            )
            db.add_all([plan, task, todo, orch])
            await db.commit()

            result = await delay_task("task-delay-1", {"minutes": 30}, db)
            await db.commit()
            reloaded_task = await db.get(ScheduleTask, "task-delay-1")
            reloaded_orch = await db.get(Orchestration, "orch-delay-1")

        assert result["data"]["status"] == "delayed"
        assert reloaded_task is not None
        assert reloaded_task.scheduled_at == scheduled_at + timedelta(minutes=30)
        assert reloaded_orch.plan["start_time"] == reloaded_task.scheduled_at.isoformat()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_submit_orchestration_carries_todo_recurrence_to_plan(monkeypatch):
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
                "recommended_id": "agent-rec-1",
                "recommended_name": "测试Agent",
            },
            "llm_reason": "ok",
        }

    monkeypatch.setattr(orchestration_api.orchestrator, "orchestrate", fake_orchestrate)
    monkeypatch.setattr(orchestration_api, "_launch_analysis", lambda *a: None)

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-rec-submit-1",
                title="带循环提交",
                source="manual",
                status="pending",
                is_recurring=True,
                recurrence_cron="0 9 * * 1-5",
                recurrence_count=2,
            )
            db.add(todo)
            await db.commit()

            result = await orchestration_api.submit_orchestration(
                orchestration_api.SubmitPayload(todo_ids=[todo.id]),
                db=db,
            )

            orch_id = result["data"]["orch_id"]
            recurrence_defaults = {
                "is_recurring": True,
                "recurrence_cron": "0 9 * * 1-5",
                "recurrence_count": 2,
            }
            await orchestration_api._process_analysis(
                db, orch_id, [todo.id], recurrence_defaults
            )
            await db.flush()
            orch = await db.get(Orchestration, orch_id)

        assert orch.plan["is_recurring"] is True
        assert orch.plan["recurrence_cron"] == "0 9 * * 1-5"
        assert orch.plan["recurrence_count"] == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_modify_params_does_not_sync_todo_recurrence_before_confirm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, Orchestration.__table__],
        )

    try:
        async with session_factory() as db:
            db.add(
                Todo(
                    id="todo-rec-modify-1",
                    title="循环隔离任务",
                    source="manual",
                    status="orchestrating",
                    orchestration_id="orch-rec-modify-1",
                    is_recurring=False,
                    recurrence_cron=None,
                    recurrence_count=0,
                )
            )
            db.add(
                Orchestration(
                    id="orch-rec-modify-1",
                    summary="循环隔离",
                    status="pending_confirm",
                    todos_snapshot=[{"id": "todo-rec-modify-1", "title": "循环隔离任务"}],
                    plan={
                        "plan_type": "agent",
                        "recommended_id": "agent-1",
                        "recommended_name": "Agent 1",
                        "is_recurring": False,
                        "recurrence_cron": None,
                        "recurrence_count": 0,
                    },
                )
            )
            await db.commit()

            await orchestration_api.modify_params(
                "orch-rec-modify-1",
                {
                    "is_recurring": True,
                    "recurrence_cron": "0 8 * * *",
                    "recurrence_count": 3,
                },
                db,
            )
            await db.commit()

            todo = await db.get(Todo, "todo-rec-modify-1")

        assert todo is not None
        assert todo.is_recurring is False
        assert todo.recurrence_cron is None
        assert todo.recurrence_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_orchestration_syncs_recurrence_to_todo_and_schedule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[*ALL_TABLES, Agent.__table__],
        )

    try:
        async with session_factory() as db:
            db.add(
                Agent(
                    id="agent-rec-confirm-1",
                    name="确认Agent",
                    dify_endpoint="https://example.com",
                    dify_api_key="secret",
                    input_params={},
                    output_params={},
                )
            )
            db.add(
                Todo(
                    id="todo-rec-confirm-1",
                    title="循环确认任务",
                    source="manual",
                    status="orchestrating",
                    orchestration_id="orch-rec-confirm-1",
                    is_recurring=False,
                    recurrence_cron=None,
                    recurrence_count=0,
                )
            )
            db.add(
                Orchestration(
                    id="orch-rec-confirm-1",
                    summary="循环确认",
                    status="pending_confirm",
                    todos_snapshot=[{"id": "todo-rec-confirm-1", "title": "循环确认任务"}],
                    plan={
                        "plan_type": "agent",
                        "recommended_id": "agent-rec-confirm-1",
                        "recommended_name": "确认Agent",
                        "input_params": {},
                        "priority": "medium",
                        "start_time": "2026-03-12T10:00:00",
                        "is_recurring": False,
                        "recurrence_cron": None,
                        "recurrence_count": 0,
                    },
                )
            )
            await db.commit()

            await orchestration_api.confirm_orchestration(
                "orch-rec-confirm-1",
                {
                    "is_recurring": True,
                    "recurrence_cron": "0 6 * * *",
                    "recurrence_count": 5,
                },
                db,
            )
            await db.commit()

            todo = await db.get(Todo, "todo-rec-confirm-1")
            plans = (await db.execute(select(SchedulePlan))).scalars().all()

        assert todo is not None
        assert todo.is_recurring is True
        assert todo.recurrence_cron == "0 6 * * *"
        assert todo.recurrence_count == 5
        assert len(plans) == 1
        assert plans[0].is_recurring is True
        assert plans[0].recurrence_cron == "0 6 * * *"
        assert plans[0].recurrence_count == 5
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_orchestration_rebalances_by_concurrency_priority_and_original_time():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                *ALL_TABLES,
                Agent.__table__,
                SystemSetting.__table__,
            ],
        )

    try:
        async with session_factory() as db:
            db.add(SystemSetting(key="max_concurrency", value={"value": 2}))
            db.add(
                Agent(
                    id="agent-confirm-rebalance",
                    name="调度Agent",
                    dify_endpoint="https://example.com",
                    dify_api_key="secret",
                    input_params={},
                    output_params={},
                )
            )
            db.add_all(
                [
                    Todo(id="todo-confirm-a", title="任务A", source="manual", status="orchestrating", orchestration_id="orch-confirm-a"),
                    Todo(id="todo-confirm-b", title="任务B", source="manual", status="orchestrating", orchestration_id="orch-confirm-b"),
                    Todo(id="todo-confirm-c", title="任务C", source="manual", status="orchestrating", orchestration_id="orch-confirm-c"),
                    Orchestration(
                        id="orch-confirm-a",
                        summary="任务A",
                        status="pending_confirm",
                        todos_snapshot=[{"id": "todo-confirm-a", "title": "任务A"}],
                        plan={
                            "plan_type": "agent",
                            "recommended_id": "agent-confirm-rebalance",
                            "recommended_name": "调度Agent",
                            "priority": "high",
                            "start_time": "2026-03-20T09:00:00",
                        },
                    ),
                    Orchestration(
                        id="orch-confirm-b",
                        summary="任务B",
                        status="pending_confirm",
                        todos_snapshot=[{"id": "todo-confirm-b", "title": "任务B"}],
                        plan={
                            "plan_type": "agent",
                            "recommended_id": "agent-confirm-rebalance",
                            "recommended_name": "调度Agent",
                            "priority": "high",
                            "start_time": "2026-03-20T09:00:00",
                        },
                    ),
                    Orchestration(
                        id="orch-confirm-c",
                        summary="任务C",
                        status="pending_confirm",
                        todos_snapshot=[{"id": "todo-confirm-c", "title": "任务C"}],
                        plan={
                            "plan_type": "agent",
                            "recommended_id": "agent-confirm-rebalance",
                            "recommended_name": "调度Agent",
                            "priority": "medium",
                            "start_time": "2026-03-20T09:00:00",
                        },
                    ),
                ]
            )
            await db.commit()

            await orchestration_api.confirm_orchestration("orch-confirm-a", db=db)
            await orchestration_api.confirm_orchestration("orch-confirm-b", db=db)
            await orchestration_api.confirm_orchestration("orch-confirm-c", db=db)
            await db.commit()

            tasks = (
                await db.execute(select(ScheduleTask).order_by(ScheduleTask.orchestration_id))
            ).scalars().all()

        by_orch = {task.orchestration_id: task for task in tasks}
        assert by_orch["orch-confirm-a"].current_scheduled_at.isoformat() == "2026-03-20T09:00:00"
        assert by_orch["orch-confirm-a"].delay_count == 0
        assert by_orch["orch-confirm-b"].current_scheduled_at.isoformat() == "2026-03-20T09:00:00"
        assert by_orch["orch-confirm-b"].delay_count == 0
        assert by_orch["orch-confirm-c"].current_scheduled_at.isoformat() == "2026-03-20T09:05:00"
        assert by_orch["orch-confirm-c"].delay_count == 1
    finally:
        await engine.dispose()
