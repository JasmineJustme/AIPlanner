from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import orchestration as orchestration_api
from app.engine.executor import executor
from app.engine.scheduler import scheduler_engine
from app.jobs import scheduler_job
from app.models.agent import Agent
from app.models.base import Base
from app.models.execution import ExecutionHistory
from app.models.schedule import SchedulePlan, ScheduleTask
from app.models.orchestration import Orchestration
from app.models.settings import SystemSetting
from app.models.todo import Todo
from app.services.dify_client import dify_client
from app.services.schedule_rebalance import rebalance_schedule_tasks


@pytest.mark.asyncio
async def test_run_tick_executes_due_pending_task_without_confirmation(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SystemSetting.__table__, SchedulePlan.__table__, ScheduleTask.__table__],
        )

    executed: list[str] = []

    async def fake_execute_task(db, task):
        executed.append(task.id)
        task.status = "running"
        task.started_at = datetime.now()
        await db.flush()

    monkeypatch.setattr(scheduler_engine, "_execute_task", fake_execute_task)

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-scheduler-1", name="测试计划", status="active")
            db.add(plan)
            db.add(
                ScheduleTask(
                    id="task-scheduler-1",
                    plan_id=plan.id,
                    orchestration_id="orch-scheduler-1",
                    status="pending",
                    priority="medium",
                    scheduled_at=datetime.now() - timedelta(minutes=1),
                )
            )
            await db.commit()

            await scheduler_engine.run_tick(db)
            await db.commit()

            task = await db.get(ScheduleTask, "task-scheduler-1")

        assert executed == ["task-scheduler-1"]
        assert task is not None
        assert task.status == "running"
        assert task.started_at is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_start_scheduler_registers_and_runs_jobs():
    if scheduler_job.scheduler.running:
        scheduler_job.stop_scheduler()

    existing_job_ids = [job.id for job in scheduler_job.scheduler.get_jobs()]
    for job_id in existing_job_ids:
        scheduler_job.scheduler.remove_job(job_id)

    scheduler_job.start_scheduler()
    try:
        job_ids = {job.id for job in scheduler_job.scheduler.get_jobs()}
        assert scheduler_job.scheduler.running is True
        assert {"scheduler_tick", "sync_tick", "auto_discover_tick"}.issubset(job_ids)
    finally:
        if scheduler_job.scheduler.running:
            scheduler_job.stop_scheduler()


@pytest.mark.asyncio
async def test_auto_discover_tick_runs_when_enabled_and_interval_elapsed(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[SystemSetting.__table__])

    called = {"count": 0}

    async def fake_smart_discover(_db):
        called["count"] += 1
        return {"created_count": 2, "dedup_count": 1, "synced_datasource_count": 1}

    monkeypatch.setattr("app.database.async_session_factory", session_factory)
    monkeypatch.setattr("app.engine.todo_discovery.todo_discovery_engine.smart_discover", fake_smart_discover)

    try:
        async with session_factory() as db:
            db.add(SystemSetting(key="auto_smart_discovery_enabled", value={"value": True}))
            db.add(SystemSetting(key="auto_smart_discovery_interval_minutes", value={"value": 5}))
            db.add(
                SystemSetting(
                    key="auto_smart_discovery_last_run_at",
                    value={"value": "2000-01-01T00:00:00"},
                )
            )
            await db.commit()

        await scheduler_job.auto_discover_tick()

        async with session_factory() as db:
            rows = (await db.execute(select(SystemSetting).where(SystemSetting.key == "auto_smart_discovery_last_run_at"))).scalars().all()
            assert len(rows) == 1
            raw = rows[0].value
            timestamp = raw.get("value") if isinstance(raw, dict) else raw
            assert isinstance(timestamp, str)
    finally:
        await engine.dispose()

    assert called["count"] == 1


@pytest.mark.asyncio
async def test_auto_discover_tick_skips_when_disabled(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[SystemSetting.__table__])

    called = {"count": 0}

    async def fake_smart_discover(_db):
        called["count"] += 1
        return {"created_count": 0}

    monkeypatch.setattr("app.database.async_session_factory", session_factory)
    monkeypatch.setattr("app.engine.todo_discovery.todo_discovery_engine.smart_discover", fake_smart_discover)

    try:
        async with session_factory() as db:
            db.add(SystemSetting(key="auto_smart_discovery_enabled", value={"value": False}))
            await db.commit()

        await scheduler_job.auto_discover_tick()
    finally:
        await engine.dispose()

    assert called["count"] == 0


@pytest.mark.asyncio
async def test_handle_failure_preserves_first_started_at_and_clears_completed_at_when_requeued():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SystemSetting.__table__, SchedulePlan.__table__, ScheduleTask.__table__],
        )

    first_started_at = datetime.now() - timedelta(minutes=2)
    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-scheduler-2", name="失败回退计划", status="active")
            db.add(plan)
            task = ScheduleTask(
                id="task-scheduler-2",
                plan_id=plan.id,
                orchestration_id="orch-scheduler-2",
                status="running",
                priority="medium",
                scheduled_at=datetime.now() - timedelta(minutes=1),
                started_at=first_started_at,
                completed_at=datetime.now() - timedelta(minutes=1),
                retry_count=0,
                max_retries=3,
            )
            db.add(task)
            await db.commit()

            await scheduler_engine._handle_failure(db, task)
            await db.commit()

            reloaded = await db.get(ScheduleTask, "task-scheduler-2")

        assert reloaded is not None
        assert reloaded.status == "pending"
        assert reloaded.started_at == first_started_at
        assert reloaded.completed_at is None
        assert reloaded.retry_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_execute_task_does_not_overwrite_started_at_on_retry(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SystemSetting.__table__, SchedulePlan.__table__, ScheduleTask.__table__, Orchestration.__table__],
        )

    first_started_at = datetime.now() - timedelta(minutes=5)

    async def fake_execute_agent(db, task):
        task.status = "completed"
        task.completed_at = datetime.now()
        await db.flush()

    monkeypatch.setattr(executor, "execute_agent", fake_execute_agent)

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-scheduler-3", name="首次开始时间保持", status="active")
            db.add(plan)
            task = ScheduleTask(
                id="task-scheduler-3",
                plan_id=plan.id,
                orchestration_id="orch-scheduler-3",
                agent_id="agent-scheduler-3",
                status="pending",
                priority="medium",
                scheduled_at=datetime.now() - timedelta(minutes=1),
                started_at=first_started_at,
                retry_count=1,
                max_retries=3,
            )
            db.add(task)
            await db.commit()

            await scheduler_engine._execute_task(db, task)
            await db.commit()

            reloaded = await db.get(ScheduleTask, "task-scheduler-3")

        assert reloaded is not None
        assert reloaded.status == "completed"
        assert reloaded.started_at == first_started_at
        assert reloaded.completed_at is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_handle_failure_sets_completed_at_on_terminal_failure():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SystemSetting.__table__, SchedulePlan.__table__, ScheduleTask.__table__],
        )

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-scheduler-4", name="最终失败完成时间", status="active")
            db.add(plan)
            task = ScheduleTask(
                id="task-scheduler-4",
                plan_id=plan.id,
                orchestration_id="orch-scheduler-4",
                status="running",
                priority="medium",
                scheduled_at=datetime.now() - timedelta(minutes=1),
                started_at=datetime.now() - timedelta(minutes=4),
                retry_count=3,
                max_retries=3,
            )
            db.add(task)
            await db.commit()

            await scheduler_engine._handle_failure(db, task)
            await db.commit()

            reloaded = await db.get(ScheduleTask, "task-scheduler-4")

        assert reloaded is not None
        assert reloaded.status == "failed"
        assert reloaded.started_at is not None
        assert reloaded.completed_at is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_execute_task_marks_linked_todo_completed(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SystemSetting.__table__, SchedulePlan.__table__, ScheduleTask.__table__, Todo.__table__, Orchestration.__table__],
        )

    async def fake_execute_agent(db, task):
        task.status = "completed"
        task.completed_at = datetime.now()
        await db.flush()

    monkeypatch.setattr(executor, "execute_agent", fake_execute_agent)

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-scheduler-5", name="完成同步计划", status="active")
            db.add(plan)
            db.add(
                Todo(
                    id="todo-scheduler-complete",
                    title="完成调度任务",
                    source="manual",
                    status="scheduling",
                    orchestration_id="orch-scheduler-complete",
                )
            )
            db.add(
                Orchestration(
                    id="orch-scheduler-complete",
                    status="confirmed",
                    todos_snapshot=[{"id": "todo-scheduler-complete", "title": "完成调度任务"}],
                )
            )
            task = ScheduleTask(
                id="task-scheduler-5",
                plan_id=plan.id,
                orchestration_id="orch-scheduler-complete",
                agent_id="agent-scheduler-5",
                status="pending",
                priority="medium",
                scheduled_at=datetime.now() - timedelta(minutes=1),
            )
            db.add(task)
            await db.commit()

            await scheduler_engine._execute_task(db, task)
            await db.commit()

            reloaded_todo = await db.get(Todo, "todo-scheduler-complete")
            reloaded_orch = await db.get(Orchestration, "orch-scheduler-complete")

        assert reloaded_todo is not None
        assert reloaded_todo.status == "completed"
        assert reloaded_todo.completed_at is not None
        assert reloaded_orch.status == "completed"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_execute_task_requeues_agent_when_dify_status_is_not_succeeded(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SystemSetting.__table__, SchedulePlan.__table__, ScheduleTask.__table__, Agent.__table__, ExecutionHistory.__table__],
        )

    async def fake_call_agent(endpoint, api_key, inputs, timeout=300):
        raise ValueError("Dify Agent execution not completed: status=failed, error=workflow failed")

    monkeypatch.setattr(dify_client, "call_agent", fake_call_agent)

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-scheduler-6", name="Dify状态校验计划", status="active")
            agent = Agent(
                id="agent-scheduler-6",
                name="Dify Agent",
                dify_endpoint="https://api.example.com/v1",
                dify_api_key="secret",
                input_params={},
                output_params={},
            )
            task = ScheduleTask(
                id="task-scheduler-6",
                plan_id=plan.id,
                orchestration_id="orch-scheduler-6",
                agent_id=agent.id,
                status="pending",
                priority="medium",
                scheduled_at=datetime.now() - timedelta(minutes=1),
                max_retries=3,
            )
            db.add_all([plan, agent, task])
            await db.commit()

            await scheduler_engine._execute_task(db, task)
            await db.commit()

            reloaded = await db.get(ScheduleTask, "task-scheduler-6")

        assert reloaded is not None
        assert reloaded.status == "pending"
        assert reloaded.retry_count == 1
        assert reloaded.completed_at is None
        assert reloaded.error_message is not None
        assert "status=failed" in reloaded.error_message
        assert reloaded.execution_log is not None
        assert '"status": "failed"' in reloaded.execution_log
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rebalance_delays_all_pending_tasks_when_running_reaches_max_concurrency():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SystemSetting.__table__, SchedulePlan.__table__, ScheduleTask.__table__],
        )

    base_time = datetime(2026, 3, 18, 10, 0, 0)
    try:
        async with session_factory() as db:
            db.add(SystemSetting(key="max_concurrency", value={"value": 1}))
            plan = SchedulePlan(id="plan-rebalance-1", name="并发占满计划", status="active")
            db.add(plan)
            db.add(
                ScheduleTask(
                    id="task-running-1",
                    plan_id=plan.id,
                    orchestration_id="orch-running-1",
                    status="running",
                    priority="high",
                    scheduled_at=base_time,
                )
            )
            db.add(
                ScheduleTask(
                    id="task-pending-1",
                    plan_id=plan.id,
                    orchestration_id="orch-pending-1",
                    status="pending",
                    priority="medium",
                    scheduled_at=base_time,
                )
            )
            await db.commit()

            await rebalance_schedule_tasks(db)
            await db.commit()
            delayed = await db.get(ScheduleTask, "task-pending-1")

        assert delayed is not None
        assert delayed.original_scheduled_at == base_time
        assert delayed.current_scheduled_at == base_time + timedelta(minutes=5)
        assert delayed.scheduled_at == base_time + timedelta(minutes=5)
        assert delayed.delay_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rebalance_prefers_priority_then_original_time_when_slots_are_limited():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SystemSetting.__table__, SchedulePlan.__table__, ScheduleTask.__table__],
        )

    slot_time = datetime(2026, 3, 18, 11, 0, 0)
    try:
        async with session_factory() as db:
            db.add(SystemSetting(key="max_concurrency", value={"value": 2}))
            plan = SchedulePlan(id="plan-rebalance-2", name="优先级重排计划", status="active")
            db.add(plan)

            # One running task occupies one slot, so pending tasks only keep one at the same time point.
            db.add(
                ScheduleTask(
                    id="task-running-2",
                    plan_id=plan.id,
                    orchestration_id="orch-running-2",
                    status="running",
                    priority="high",
                    scheduled_at=slot_time,
                )
            )
            db.add_all(
                [
                    ScheduleTask(
                        id="task-high-earlier",
                        plan_id=plan.id,
                        orchestration_id="orch-priority-1",
                        status="pending",
                        priority="high",
                        scheduled_at=slot_time,
                        original_scheduled_at=slot_time - timedelta(minutes=10),
                        current_scheduled_at=slot_time,
                    ),
                    ScheduleTask(
                        id="task-high-later",
                        plan_id=plan.id,
                        orchestration_id="orch-priority-2",
                        status="pending",
                        priority="high",
                        scheduled_at=slot_time,
                        original_scheduled_at=slot_time - timedelta(minutes=5),
                        current_scheduled_at=slot_time,
                    ),
                    ScheduleTask(
                        id="task-medium",
                        plan_id=plan.id,
                        orchestration_id="orch-priority-3",
                        status="pending",
                        priority="medium",
                        scheduled_at=slot_time,
                        original_scheduled_at=slot_time - timedelta(minutes=20),
                        current_scheduled_at=slot_time,
                    ),
                ]
            )
            await db.commit()

            await rebalance_schedule_tasks(db)
            await db.commit()

            high_earlier = await db.get(ScheduleTask, "task-high-earlier")
            high_later = await db.get(ScheduleTask, "task-high-later")
            medium = await db.get(ScheduleTask, "task-medium")

        assert high_earlier is not None
        assert high_later is not None
        assert medium is not None

        assert high_earlier.current_scheduled_at == slot_time
        assert high_earlier.delay_count == 0

        assert high_later.current_scheduled_at == slot_time + timedelta(minutes=5)
        assert high_later.delay_count == 1

        assert medium.current_scheduled_at == slot_time + timedelta(minutes=10)
        assert medium.delay_count == 2
    finally:
        await engine.dispose()


