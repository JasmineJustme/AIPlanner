from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import Agent, ExecutionHistory, Orchestration, SchedulePlan, ScheduleTask, Todo, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _todo_user_filter(current_user: User):
    return Todo.creator_id == current_user.id


def _schedule_user_filter(current_user: User):
    return Orchestration.user_id == current_user.id


def _history_user_filter(current_user: User):
    return Orchestration.user_id == current_user.id


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    todo_filter = _todo_user_filter(current_user)
    todo_where = [Todo.execution_mode == "user", Todo.status.in_(["pending_confirm", "pending"]), todo_filter]
    completed_where = [Todo.status == "completed", Todo.completed_at.is_not(None), Todo.completed_at >= today_start, Todo.completed_at < tomorrow_start, todo_filter]
    today_todo_result = await db.execute(select(func.count()).select_from(Todo).where(*todo_where))
    pending_confirm_result = await db.execute(
        select(func.count()).select_from(Todo).where(Todo.status == "pending_confirm", todo_filter)
    )
    scheduling_result = await db.execute(
        select(func.count())
        .select_from(ScheduleTask)
        .join(Orchestration, Orchestration.id == ScheduleTask.orchestration_id)
        .where(ScheduleTask.status.in_(["pending", "running", "failed", "blocked"]), _schedule_user_filter(current_user))
    )
    today_completed_result = await db.execute(select(func.count()).select_from(Todo).where(*completed_where))
    failed_result = await db.execute(
        select(func.count())
        .select_from(ScheduleTask)
        .join(Orchestration, Orchestration.id == ScheduleTask.orchestration_id)
        .where(ScheduleTask.status == "failed", _schedule_user_filter(current_user))
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
    current_user=Depends(get_current_user),
):
    now = datetime.now().replace(microsecond=0)
    result = await db.execute(
        select(ScheduleTask, SchedulePlan.name)
        .join(SchedulePlan, SchedulePlan.id == ScheduleTask.plan_id, isouter=True)
        .join(Orchestration, Orchestration.id == ScheduleTask.orchestration_id)
        .where(ScheduleTask.status == "pending", _schedule_user_filter(current_user))
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
    current_user=Depends(get_current_user),
):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = today - timedelta(days=6)

    date_str_col = func.date(Todo.completed_at)
    todo_filter = _todo_user_filter(current_user)
    where_args = [Todo.status == "completed", Todo.completed_at.is_not(None), Todo.completed_at >= start_date, Todo.completed_at < today + timedelta(days=1), todo_filter]
    result = await db.execute(
        select(date_str_col.label("day"), func.count().label("cnt"))
        .where(*where_args)
        .group_by(date_str_col)
        .order_by(date_str_col)
    )
    rows = {row.day: row.cnt for row in result.all()}

    data = []
    for offset in range(7):
        d = (start_date + timedelta(days=offset)).date().isoformat()
        data.append({"date": d, "count": rows.get(d, 0)})

    return {"code": 200, "message": "success", "data": data}


@router.get("/agent-ranking")
async def get_agent_ranking(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(
            func.coalesce(ExecutionHistory.agent_name, Agent.name).label("name"),
            func.count().label("count"),
        )
        .select_from(ExecutionHistory)
        .outerjoin(Agent, Agent.id == ExecutionHistory.agent_id)
        .join(Orchestration, Orchestration.id == ExecutionHistory.task_id)
        .where(ExecutionHistory.agent_id.is_not(None), _history_user_filter(current_user))
        .group_by(func.coalesce(ExecutionHistory.agent_name, Agent.name))
        .order_by(func.count().desc())
        .limit(10)
    )
    history_rows = result.all()

    if history_rows:
        data = [{"name": r.name or "未知Agent", "count": r.count} for r in history_rows]
    else:
        agent_result = await db.execute(
            select(Agent.name, Agent.call_count)
            .join(ExecutionHistory, ExecutionHistory.agent_id == Agent.id)
            .join(Orchestration, Orchestration.id == ExecutionHistory.task_id)
            .where(Agent.call_count > 0, _history_user_filter(current_user))
            .group_by(Agent.name, Agent.call_count)
            .order_by(Agent.call_count.desc())
            .limit(10)
        )
        data = [
            {"name": r.name, "count": r.call_count}
            for r in agent_result.all()
        ]

    return {"code": 200, "message": "success", "data": data}
