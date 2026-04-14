import math
from datetime import datetime, timedelta

from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import SchedulePlan, ScheduleTask
from app.utils.recurrence import get_next_run_time
from app.models.settings import SystemSetting
from app.engine.executor import executor
from app.services.sse_manager import sse_manager
from app.utils.timezone import utc_now_naive
from loguru import logger


def _now_local_naive() -> datetime:
    return utc_now_naive()


class SchedulerEngine:
    def __init__(self):
        self._circuit_breaker: dict[str, int] = {}  # agent_id -> consecutive failures

    async def _materialize_recurring_runs(self, db: AsyncSession, now: datetime) -> None:
        parent_q = select(ScheduleTask).where(
            ScheduleTask.is_parent.is_(True),
            ScheduleTask.status.in_(["pending", "running", "recurring"]),
            or_(
                ScheduleTask.current_scheduled_at <= now,
                ScheduleTask.current_scheduled_at.is_(None),
            ),
        )
        parent_tasks = (await db.execute(parent_q)).scalars().all()

        for parent in parent_tasks:
            running_child_q = select(func.count()).select_from(ScheduleTask).where(
                ScheduleTask.parent_task_id == parent.id,
                ScheduleTask.status == "running",
            )
            running_children = (await db.execute(running_child_q)).scalar() or 0
            if running_children > 0:
                continue

            limit = int(parent.recurrence_limit or 0)
            done = int(parent.recurrence_done or 0)
            if limit > 0 and done >= limit:
                parent.status = "completed"
                if parent.completed_at is None:
                    parent.completed_at = now
                continue

            existing_open_child_q = select(ScheduleTask).where(
                ScheduleTask.parent_task_id == parent.id,
                ScheduleTask.status.in_(["pending", "running", "retrying", "paused", "confirming"]),
            )
            existing_open_child = (await db.execute(existing_open_child_q)).scalars().first()
            if existing_open_child is not None:
                continue

            execute_at = parent.current_scheduled_at or parent.scheduled_at or now
            if execute_at < now:
                execute_at = now

            child = ScheduleTask(
                plan_id=parent.plan_id,
                parent_task_id=parent.id,
                is_parent=False,
                orchestration_id=parent.orchestration_id,
                agent_id=parent.agent_id,
                wagent_id=parent.wagent_id,
                status="pending",
                priority=parent.priority,
                scheduled_at=execute_at,
                original_scheduled_at=execute_at,
                current_scheduled_at=execute_at,
                delay_count=0,
                input_params=dict(parent.input_params or {}),
                recurrence_cron=parent.recurrence_cron,
                recurrence_limit=limit,
                recurrence_done=done,
            )
            db.add(child)
            parent.status = "recurring"

        await db.flush()

    async def run_tick(self, db: AsyncSession) -> None:
        """Main scheduler loop - called by APScheduler every minute"""
        if not await self._in_time_window(db):
            return

        now = _now_local_naive()
        await self._materialize_recurring_runs(db, now)

        max_concurrent = await self._get_setting(db, "max_concurrency", 3)
        running_q = select(func.count()).select_from(ScheduleTask).where(
            ScheduleTask.status == "running",
            ScheduleTask.is_parent.is_(False),
        )
        running = (await db.execute(running_q)).scalar() or 0

        available_slots = max_concurrent - running
        if available_slots <= 0:
            return

        pending_q = (
            select(ScheduleTask)
            .where(
                ScheduleTask.is_parent.is_(False),
                ScheduleTask.status == "pending",
                or_(
                    ScheduleTask.current_scheduled_at <= now,
                    ScheduleTask.current_scheduled_at.is_(None),
                ),
            )
            .order_by(
                ScheduleTask.priority.desc(),
                ScheduleTask.current_scheduled_at,
                ScheduleTask.original_scheduled_at,
            )
            .limit(available_slots)
        )
        tasks = (await db.execute(pending_q)).scalars().all()

        for task in tasks:
            if not await self._check_dependencies(db, task):
                continue

            breaker_id = str(task.agent_id or task.wagent_id or "")
            if breaker_id and self._circuit_breaker.get(breaker_id, 0) >= 5:
                task.status = "blocked"
                await sse_manager.broadcast("circuit_breaker.triggered", {"task_id": task.id})
                continue

            await self._execute_task(db, task)

    async def _execute_task(self, db: AsyncSession, task: ScheduleTask) -> None:
        task.status = "running"
        if task.started_at is None:
            task.started_at = _now_local_naive()
        task.completed_at = None
        task.error_message = None
        await db.flush()

        await sse_manager.broadcast("task.status_changed", {"task_id": task.id, "status": "running"})

        try:
            if task.agent_id:
                await executor.execute_agent(db, task)
            elif task.wagent_id:
                await executor.execute_wagent(db, task)

            if task.status == "completed":
                breaker_id = str(task.agent_id or task.wagent_id or "")
                if breaker_id:
                    self._circuit_breaker[breaker_id] = 0
                await self._after_child_completion(db, task)
                await sse_manager.broadcast("task.status_changed", {"task_id": task.id, "status": "completed"})
            else:
                await self._handle_failure(db, task)
        except Exception as e:
            logger.error(f"Task execution error: {e}")
            await self._handle_failure(db, task)

    async def _after_child_completion(self, db: AsyncSession, task: ScheduleTask) -> None:
        now = _now_local_naive()
        if not task.parent_task_id:
            if task.orchestration_id:
                from app.api.orchestration import sync_todos_for_orchestration, update_orchestration_status

                if await update_orchestration_status(db, task.orchestration_id, "completed"):
                    await sync_todos_for_orchestration(db, task.orchestration_id)
            return

        parent = await db.get(ScheduleTask, task.parent_task_id)
        if not parent:
            return

        parent.recurrence_done = int(parent.recurrence_done or 0) + 1
        parent.started_at = parent.started_at or task.started_at or now
        parent.completed_at = task.completed_at or now

        limit = int(parent.recurrence_limit or 0)
        if limit > 0 and parent.recurrence_done >= limit:
            parent.status = "completed"
            if parent.orchestration_id:
                from app.api.orchestration import sync_todos_for_orchestration, update_orchestration_status

                if await update_orchestration_status(db, parent.orchestration_id, "completed"):
                    await sync_todos_for_orchestration(db, parent.orchestration_id)
            return

        if parent.recurrence_cron:
            try:
                next_run = get_next_run_time(parent.recurrence_cron, parent.current_scheduled_at or now)
            except Exception:
                next_run = now + timedelta(minutes=1)
        else:
            next_run = now + timedelta(minutes=1)

        parent.current_scheduled_at = next_run
        parent.scheduled_at = next_run
        parent.status = "recurring"
        await db.flush()

    async def _handle_failure(self, db: AsyncSession, task: ScheduleTask) -> None:
        breaker_id = str(task.agent_id or task.wagent_id or "")
        if breaker_id:
            self._circuit_breaker[breaker_id] = self._circuit_breaker.get(breaker_id, 0) + 1

        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = "retrying"
            # Exponential backoff
            delay_minutes = math.pow(2, task.retry_count - 1)
            next_run_at = _now_local_naive() + timedelta(minutes=delay_minutes)
            if task.original_scheduled_at is None:
                task.original_scheduled_at = task.scheduled_at
            task.current_scheduled_at = next_run_at
            task.scheduled_at = next_run_at
            task.delay_count = int(task.delay_count or 0) + 1
            task.status = "pending"
            task.completed_at = None
        else:
            task.status = "failed"
            if task.completed_at is None:
                task.completed_at = _now_local_naive()

        await db.flush()
        await sse_manager.broadcast("task.status_changed", {"task_id": task.id, "status": task.status})

    async def _check_dependencies(self, db: AsyncSession, task: ScheduleTask) -> bool:
        if not task.dependencies:
            return True
        dep_ids = task.dependencies if isinstance(task.dependencies, list) else []
        for dep_id in dep_ids:
            dep = await db.get(ScheduleTask, dep_id)
            if dep and dep.status != "completed":
                if dep.status == "failed":
                    task.status = "blocked"
                    await db.flush()
                return False
        return True

    async def _needs_confirmation(self, db: AsyncSession, task: ScheduleTask) -> bool:
        return False

    async def _in_time_window(self, db: AsyncSession) -> bool:
        # Simplified: always allow for now
        return True

    async def _get_setting(self, db: AsyncSession, key: str, default=None):
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
        setting = result.scalar_one_or_none()
        if not setting:
            return default
        val = setting.value
        if isinstance(val, dict) and "value" in val:
            return val["value"]
        return val if val is not None else default


scheduler_engine = SchedulerEngine()
