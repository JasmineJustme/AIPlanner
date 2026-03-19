from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import SchedulePlan, ScheduleTask, Todo

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    today_todo_result = await db.execute(
        select(func.count()).select_from(Todo).where(
            Todo.execution_mode == "user",
            Todo.status.in_(["pending_confirm", "pending"]),
        )
    )
    pending_confirm_result = await db.execute(
        select(func.count()).select_from(Todo).where(Todo.status == "pending_confirm")
    )
    scheduling_result = await db.execute(
        select(func.count()).select_from(ScheduleTask).where(
            ScheduleTask.status.in_(["pending", "running", "failed", "blocked"])
        )
    )
    today_completed_result = await db.execute(
        select(func.count()).select_from(Todo).where(
            Todo.status == "completed",
            Todo.completed_at.is_not(None),
            Todo.completed_at >= today_start,
            Todo.completed_at < tomorrow_start,
        )
    )
    failed_result = await db.execute(
        select(func.count()).select_from(ScheduleTask).where(ScheduleTask.status == "failed")
    )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "today_todo": int(today_todo_result.scalar() or 0),
            "pending_confirm": int(pending_confirm_result.scalar() or 0),
            "running": int(scheduling_result.scalar() or 0),
            "today_completed": int(today_completed_result.scalar() or 0),
            "failed": int(failed_result.scalar() or 0),
        },
    }


@router.get("/next-task")
async def get_next_task(
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now().replace(microsecond=0)
    result = await db.execute(
        select(ScheduleTask, SchedulePlan.name)
        .join(SchedulePlan, SchedulePlan.id == ScheduleTask.plan_id, isouter=True)
        .where(ScheduleTask.status == "pending")
    )
    rows = result.all()

    if not rows:
        return {
            "code": 200,
            "message": "success",
            "data": None,
        }

    selected_task = None
    selected_plan_name = None
    selected_time = None
    selected_distance = float("inf")

    for task, plan_name in rows:
        run_at = task.current_scheduled_at or task.scheduled_at
        if not run_at:
            continue
        distance = abs((run_at - now).total_seconds())
        if distance < selected_distance:
            selected_distance = distance
            selected_task = task
            selected_plan_name = plan_name
            selected_time = run_at

    if selected_task is None or selected_time is None:
        return {
            "code": 200,
            "message": "success",
            "data": None,
        }

    countdown_seconds = max(0, int((selected_time - now).total_seconds()))
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": selected_task.id,
            "name": selected_plan_name or f"调度任务 {selected_task.id}",
            "scheduled_at": selected_time.isoformat(),
            "countdown_seconds": countdown_seconds,
        },
    }


@router.get("/trend")
async def get_trend(
    db: AsyncSession = Depends(get_db),
):
    return {
        "code": 200,
        "message": "success",
        "data": [
            {"date": "2025-03-01", "completed": 5, "pending": 10},
            {"date": "2025-03-02", "completed": 8, "pending": 7},
            {"date": "2025-03-03", "completed": 12, "pending": 3},
        ],
    }


@router.get("/agent-ranking")
async def get_agent_ranking(
    db: AsyncSession = Depends(get_db),
):
    return {
        "code": 200,
        "message": "success",
        "data": [
            {"agent_id": "a1", "name": "Agent A", "success_count": 45, "rank": 1},
            {"agent_id": "a2", "name": "Agent B", "success_count": 32, "rank": 2},
        ],
    }


@router.get("/sync-status")
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
):
    return {
        "code": 200,
        "message": "success",
        "data": {
            "email": {"last_sync": "2025-03-03T10:00:00Z", "status": "success"},
            "wechat": {"last_sync": "2025-03-03T09:30:00Z", "status": "success"},
            "in_app": {"last_sync": None, "status": "idle"},
        },
    }
