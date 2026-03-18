from __future__ import annotations

from datetime import timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import ScheduleTask
from app.models.settings import SystemSetting

_PRIORITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}
_DELAY_STEP = timedelta(minutes=5)


def _priority_weight(priority: str | None) -> int:
    return _PRIORITY_WEIGHT.get(str(priority or "").lower(), 0)


async def _get_max_concurrency(db: AsyncSession, default: int = 3) -> int:
    try:
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == "max_concurrency"))
    except SQLAlchemyError:
        return default
    setting = result.scalar_one_or_none()
    if not setting:
        return default
    value = setting.value
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _sort_key(task: ScheduleTask) -> tuple:
    # current_scheduled_at first; same time prefers higher priority, then older original plan time.
    return (
        task.current_scheduled_at,
        -_priority_weight(task.priority),
        task.original_scheduled_at,
        task.created_at,
        task.id,
    )


async def rebalance_schedule_tasks(db: AsyncSession) -> None:
    max_concurrency = await _get_max_concurrency(db)

    running_result = await db.execute(select(ScheduleTask).where(ScheduleTask.status == "running"))
    running_tasks = running_result.scalars().all()
    running_count = len(running_tasks)

    pending_result = await db.execute(
        select(ScheduleTask).where(ScheduleTask.status.in_(["pending", "retrying"]))
    )
    pending_tasks = pending_result.scalars().all()
    if not pending_tasks:
        return

    available_slots = max(max_concurrency - running_count, 0)

    # Backfill new timeline fields for historical rows.
    for task in pending_tasks:
        if task.original_scheduled_at is None:
            task.original_scheduled_at = task.scheduled_at
        if task.current_scheduled_at is None:
            task.current_scheduled_at = task.scheduled_at
        if task.delay_count is None:
            task.delay_count = 0

    if available_slots <= 0:
        for task in pending_tasks:
            task.current_scheduled_at = task.current_scheduled_at + _DELAY_STEP
            task.scheduled_at = task.current_scheduled_at
            task.delay_count = int(task.delay_count or 0) + 1
        await db.flush()
        return

    # Keep processing time slots in ascending order; overflow tasks are delayed by fixed 5 minutes.
    buckets: dict = {}
    for task in pending_tasks:
        buckets.setdefault(task.current_scheduled_at, []).append(task)

    while buckets:
        current_time = min(buckets.keys())
        tasks_at_time = buckets.pop(current_time)
        tasks_at_time.sort(
            key=lambda t: (
                -_priority_weight(t.priority),
                t.original_scheduled_at,
                t.created_at,
                t.id,
            )
        )

        overflow_tasks = tasks_at_time[available_slots:]

        for task in overflow_tasks:
            task.current_scheduled_at = task.current_scheduled_at + _DELAY_STEP
            task.scheduled_at = task.current_scheduled_at
            task.delay_count = int(task.delay_count or 0) + 1
            buckets.setdefault(task.current_scheduled_at, []).append(task)

    # Stable ordering is expected by several list APIs.
    pending_tasks.sort(key=_sort_key)
    await db.flush()




