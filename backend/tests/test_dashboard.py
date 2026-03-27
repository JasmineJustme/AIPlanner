from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dashboard import get_dashboard_stats, get_next_task
from app.models.base import Base
from app.models.schedule import SchedulePlan, ScheduleTask
from app.models.todo import Todo


@pytest.mark.asyncio
async def test_dashboard_stats_match_requested_metrics():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, SchedulePlan.__table__, ScheduleTask.__table__],
        )

    now = datetime.now().replace(microsecond=0)

    try:
        async with session_factory() as db:
            db.add_all(
                [
                    Todo(id="todo-1", title="o", source="manual", execution_mode="system", status="orchestrating"),
                    Todo(id="todo-2", title="s", source="manual", execution_mode="system", status="scheduling"),
                    Todo(id="todo-3", title="p", source="manual", execution_mode="user", status="pending"),
                    Todo(id="todo-4", title="pc", source="manual", execution_mode="user", status="pending_confirm"),
                    Todo(id="todo-5", title="c1", source="manual", execution_mode="user", status="completed", completed_at=now - timedelta(hours=1)),
                    Todo(id="todo-6", title="c2", source="manual", execution_mode="user", status="completed", completed_at=now - timedelta(days=1)),
                ]
            )

            plan = SchedulePlan(id="plan-1", name="计划A", status="active")
            db.add(plan)
            db.add_all(
                [
                    ScheduleTask(
                        id="task-1",
                        plan_id=plan.id,
                        orchestration_id="orch-1",
                        status="pending",
                        priority="medium",
                        scheduled_at=now + timedelta(minutes=5),
                        current_scheduled_at=now + timedelta(minutes=5),
                    ),
                    ScheduleTask(
                        id="task-2",
                        plan_id=plan.id,
                        orchestration_id="orch-2",
                        status="running",
                        priority="medium",
                        scheduled_at=now + timedelta(minutes=10),
                        current_scheduled_at=now + timedelta(minutes=10),
                    ),
                    ScheduleTask(
                        id="task-3",
                        plan_id=plan.id,
                        orchestration_id="orch-3",
                        status="failed",
                        priority="medium",
                        scheduled_at=now + timedelta(minutes=15),
                        current_scheduled_at=now + timedelta(minutes=15),
                    ),
                    ScheduleTask(
                        id="task-4",
                        plan_id=plan.id,
                        orchestration_id="orch-4",
                        status="blocked",
                        priority="medium",
                        scheduled_at=now + timedelta(minutes=20),
                        current_scheduled_at=now + timedelta(minutes=20),
                    ),
                    ScheduleTask(
                        id="task-5",
                        plan_id=plan.id,
                        orchestration_id="orch-5",
                        status="completed",
                        priority="medium",
                        scheduled_at=now - timedelta(minutes=5),
                        current_scheduled_at=now - timedelta(minutes=5),
                    ),
                ]
            )
            await db.commit()

            result = await get_dashboard_stats(db)

        data = result["data"]
        assert data["today_todo"] == 2
        assert data["pending_confirm"] == 1
        assert data["running"] == 4
        assert data["today_completed"] == 1
        assert data["failed"] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_next_task_returns_pending_task_closest_to_now_by_current_schedule_time():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SchedulePlan.__table__, ScheduleTask.__table__],
        )

    now = datetime.now().replace(microsecond=0)

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-next", name="最近任务计划", status="active")
            db.add(plan)
            db.add_all(
                [
                    ScheduleTask(
                        id="task-next-1",
                        plan_id=plan.id,
                        orchestration_id="orch-next-1",
                        status="pending",
                        priority="medium",
                        scheduled_at=now + timedelta(minutes=30),
                        current_scheduled_at=now + timedelta(minutes=30),
                    ),
                    ScheduleTask(
                        id="task-next-2",
                        plan_id=plan.id,
                        orchestration_id="orch-next-2",
                        status="pending",
                        priority="medium",
                        scheduled_at=now + timedelta(minutes=3),
                        current_scheduled_at=now + timedelta(minutes=3),
                    ),
                    ScheduleTask(
                        id="task-next-3",
                        plan_id=plan.id,
                        orchestration_id="orch-next-3",
                        status="running",
                        priority="medium",
                        scheduled_at=now + timedelta(minutes=1),
                        current_scheduled_at=now + timedelta(minutes=1),
                    ),
                ]
            )
            await db.commit()

            result = await get_next_task(db)

        payload = result["data"]
        assert payload is not None
        assert payload["id"] == "task-next-2"
        assert payload["name"] == "最近任务计划"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_next_task_returns_none_when_no_pending_tasks():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SchedulePlan.__table__, ScheduleTask.__table__],
        )

    now = datetime.now().replace(microsecond=0)

    try:
        async with session_factory() as db:
            plan = SchedulePlan(id="plan-none", name="无待执行计划", status="active")
            db.add(plan)
            db.add(
                ScheduleTask(
                    id="task-none-1",
                    plan_id=plan.id,
                    orchestration_id="orch-none-1",
                    status="running",
                    priority="medium",
                    scheduled_at=now,
                    current_scheduled_at=now,
                )
            )
            await db.commit()

            result = await get_next_task(db)

        assert result["data"] is None
    finally:
        await engine.dispose()

