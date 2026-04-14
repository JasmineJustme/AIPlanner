from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ScheduleTask, SchedulePlan, Agent, WAgent, Todo
from app.utils.timezone import utc_now_naive, utc_to_beijing_iso

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


def _now_local_naive() -> datetime:
    return utc_now_naive()


def _resolve_task_title(t: ScheduleTask, todo_titles_by_orch: dict[str, list[str]], plan_name: str | None = None, agent_name: str | None = None) -> str:
    titles = todo_titles_by_orch.get(t.orchestration_id, [])
    first_title = next((title.strip() for title in titles if isinstance(title, str) and title.strip()), "")
    if first_title:
        return first_title
    if plan_name:
        return plan_name
    if agent_name:
        return agent_name
    return f"Task {t.id[:8]}"


def _task_to_dict(
    t: ScheduleTask,
    agent_name: str | None = None,
    plan_name: str | None = None,
    task_title: str | None = None,
) -> dict:
    return {
        "id": t.id,
        "plan_id": t.plan_id,
        "plan_name": plan_name,
        "task_title": task_title,
        "is_parent": bool(getattr(t, "is_parent", False)),
        "parent_task_id": getattr(t, "parent_task_id", None),
        "recurrence_cron": getattr(t, "recurrence_cron", None),
        "recurrence_limit": int(getattr(t, "recurrence_limit", 0) or 0),
        "recurrence_done": int(getattr(t, "recurrence_done", 0) or 0),
        "orchestration_id": t.orchestration_id,
        "agent_id": t.agent_id,
        "wagent_id": t.wagent_id,
        "agent_name": agent_name,
        "wagent_version": t.wagent_version,
        "status": t.status,
        "priority": t.priority,
        "scheduled_at": utc_to_beijing_iso(t.scheduled_at),
        "original_scheduled_at": utc_to_beijing_iso(t.original_scheduled_at),
        "current_scheduled_at": utc_to_beijing_iso(t.current_scheduled_at),
        "delay_count": int(t.delay_count or 0),
        "started_at": utc_to_beijing_iso(t.started_at),
        "completed_at": utc_to_beijing_iso(t.completed_at),
        "input_params": t.input_params,
        "output_result": t.output_result,
        "error_message": t.error_message,
        "retry_count": t.retry_count,
        "max_retries": t.max_retries,
        "dependencies": t.dependencies or [],
        "execution_log": t.execution_log,
        "created_at": utc_to_beijing_iso(t.created_at),
        "updated_at": utc_to_beijing_iso(t.updated_at),
    }


@router.get("/plans")
async def list_plans(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SchedulePlan).order_by(SchedulePlan.created_at.desc()))
    items = result.scalars().all()
    data = [
        {
            "id": p.id,
            "name": p.name,
            "status": p.status,
            "is_recurring": p.is_recurring,
            "recurrence_cron": p.recurrence_cron,
            "next_run_at": utc_to_beijing_iso(p.next_run_at),
        }
        for p in items
    ]
    return {"code": 200, "message": "success", "data": data}


@router.get("/tasks")
async def list_schedule_tasks(
    status: str | None = None,
    plan_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(ScheduleTask).order_by(ScheduleTask.current_scheduled_at.desc())
    if status:
        q = q.where(ScheduleTask.status == status)
    else:
        q = q.where(ScheduleTask.status != "cancelled")
    if plan_id:
        q = q.where(ScheduleTask.plan_id == plan_id)
    result = await db.execute(q)
    items = result.scalars().all()

    plans = {}
    if items:
        plan_ids = list({t.plan_id for t in items})
        plans_result = await db.execute(select(SchedulePlan).where(SchedulePlan.id.in_(plan_ids)))
        for p in plans_result.scalars().all():
            plans[p.id] = p.name

    orchestration_ids = [t.orchestration_id for t in items if t.orchestration_id]
    todo_titles_by_orch: dict[str, list[str]] = {}
    if orchestration_ids:
        todo_result = await db.execute(select(Todo).where(Todo.orchestration_id.in_(orchestration_ids)))
        for todo in todo_result.scalars().all():
            todo_titles_by_orch.setdefault(todo.orchestration_id or "", []).append(todo.title)

    agent_ids = [t.agent_id for t in items if t.agent_id]
    wagent_ids = [t.wagent_id for t in items if t.wagent_id]
    agents_map = {}
    if agent_ids:
        agents_result = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
        for a in agents_result.scalars().all():
            agents_map[a.id] = a.name
    if wagent_ids:
        wagents_result = await db.execute(select(WAgent).where(WAgent.id.in_(wagent_ids)))
        for w in wagents_result.scalars().all():
            agents_map[w.id] = w.name

    data = [
        _task_to_dict(
            t,
            agent_name=agents_map.get(t.agent_id or t.wagent_id or ""),
            plan_name=plans.get(t.plan_id),
            task_title=_resolve_task_title(
                t,
                todo_titles_by_orch,
                plan_name=plans.get(t.plan_id),
                agent_name=agents_map.get(t.agent_id or t.wagent_id or ""),
            ),
        )
        for t in items
    ]
    return {"code": 200, "message": "success", "data": data}


@router.get("/tasks/{task_id}")
async def get_task_detail(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ScheduleTask).where(ScheduleTask.id == task_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    agent_name = None
    if t.agent_id:
        a = await db.get(Agent, t.agent_id)
        agent_name = a.name if a else None
    elif t.wagent_id:
        w = await db.get(WAgent, t.wagent_id)
        agent_name = w.name if w else None
    plan_name = None
    if t.plan_id:
        p = await db.get(SchedulePlan, t.plan_id)
        plan_name = p.name if p else None
    todo_titles_by_orch: dict[str, list[str]] = {}
    if t.orchestration_id:
        todo_result = await db.execute(select(Todo).where(Todo.orchestration_id == t.orchestration_id))
        todo_titles_by_orch[t.orchestration_id] = [todo.title for todo in todo_result.scalars().all()]
    return {
        "code": 200,
        "message": "success",
        "data": _task_to_dict(
            t,
            agent_name=agent_name,
            plan_name=plan_name,
            task_title=_resolve_task_title(t, todo_titles_by_orch, plan_name=plan_name, agent_name=agent_name),
        ),
    }


@router.post("/plans/{plan_id}/pause")
async def pause_plan(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
):
    plan = await db.get(SchedulePlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan.status = "paused"
    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "paused"}}


@router.post("/plans/{plan_id}/resume")
async def resume_plan(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
):
    plan = await db.get(SchedulePlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan.status = "active"
    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "active"}}


@router.post("/plans/{plan_id}/cancel")
async def cancel_plan(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
):
    plan = await db.get(SchedulePlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    task_result = await db.execute(select(ScheduleTask).where(ScheduleTask.plan_id == plan_id))
    plan_tasks = task_result.scalars().all()
    orchestration_ids = {task.orchestration_id for task in plan_tasks if task.orchestration_id}

    if orchestration_ids:
        from app.api.orchestration import sync_todos_for_orchestration, update_orchestration_status

        for orch_id in orchestration_ids:
            if await update_orchestration_status(db, orch_id, "pending_confirm"):
                await sync_todos_for_orchestration(db, orch_id)

    for task in plan_tasks:
        await db.delete(task)
    await db.flush()

    await db.delete(plan)
    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "cancelled", "removed": True}}


@router.get("/gantt")
async def get_gantt_data(
    plan_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(ScheduleTask)
        .where(
            ScheduleTask.status != "cancelled",
            or_(ScheduleTask.is_parent.is_(False), ScheduleTask.is_parent.is_(None)),
        )
        .order_by(ScheduleTask.current_scheduled_at)
    )
    if plan_id:
        q = q.where(ScheduleTask.plan_id == plan_id)
    result = await db.execute(q)
    items = result.scalars().all()

    orchestration_ids = [t.orchestration_id for t in items if t.orchestration_id]
    todo_titles_by_orch: dict[str, list[str]] = {}
    if orchestration_ids:
        todo_result = await db.execute(select(Todo).where(Todo.orchestration_id.in_(orchestration_ids)))
        for todo in todo_result.scalars().all():
            todo_titles_by_orch.setdefault(todo.orchestration_id or "", []).append(todo.title)

    agent_ids = [t.agent_id for t in items if t.agent_id]
    wagent_ids = [t.wagent_id for t in items if t.wagent_id]
    agents_map = {}
    if agent_ids:
        agents_result = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
        for a in agents_result.scalars().all():
            agents_map[a.id] = a.name
    if wagent_ids:
        wagents_result = await db.execute(select(WAgent).where(WAgent.id.in_(wagent_ids)))
        for w in wagents_result.scalars().all():
            agents_map[w.id] = w.name

    plan_names = {}
    if items:
        plan_ids = list({t.plan_id for t in items if t.plan_id})
        plans_result = await db.execute(select(SchedulePlan).where(SchedulePlan.id.in_(plan_ids)))
        for p in plans_result.scalars().all():
            plan_names[p.id] = p.name

    tasks = []
    for t in items:
        resolved_agent_name = agents_map.get(t.agent_id or t.wagent_id or "")
        name = _resolve_task_title(t, todo_titles_by_orch, plan_name=plan_names.get(t.plan_id), agent_name=resolved_agent_name)
        start = t.current_scheduled_at or t.scheduled_at
        end = t.completed_at or t.started_at or t.current_scheduled_at or t.scheduled_at
        if end == start and start:
            from datetime import timedelta
            end = start + timedelta(hours=1)
        tasks.append({
            "id": t.id,
            "name": name,
            "task_title": name,
            "start": utc_to_beijing_iso(start),
            "end": utc_to_beijing_iso(end),
            "status": t.status,
            "priority": t.priority,
        })
    return {"code": 200, "message": "success", "data": {"tasks": tasks}}


@router.post("/tasks/{task_id}/confirm-execute")
async def confirm_execute(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(ScheduleTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "recurring" if bool(getattr(task, "is_parent", False)) else "pending"
    task.confirm_action = "confirmed"
    task.confirm_deadline = None
    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "confirmed"}}


@router.post("/tasks/{task_id}/delay")
async def delay_task(
    task_id: str,
    payload: dict = Body(default={"minutes": 30}),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta
    task = await db.get(ScheduleTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    minutes = int(payload.get("minutes", 30) or 30)
    now = _now_local_naive()
    current_time = task.current_scheduled_at or task.scheduled_at
    base_time = current_time if current_time and current_time > now else now
    if task.original_scheduled_at is None:
        task.original_scheduled_at = task.scheduled_at
    task.current_scheduled_at = base_time + timedelta(minutes=minutes)
    task.scheduled_at = task.current_scheduled_at
    task.delay_count = int(task.delay_count or 0) + 1
    task.status = "recurring" if bool(getattr(task, "is_parent", False)) else "pending"
    task.confirm_action = "delayed"
    task.confirm_deadline = None

    if task.orchestration_id:
        from app.api.orchestration import get_orchestration, _normalize_plan_time_value

        orch = await get_orchestration(db, task.orchestration_id)
        if orch and orch.plan is not None:
            plan = dict(orch.plan)
            plan["start_time"] = _normalize_plan_time_value(task.current_scheduled_at.isoformat(), assume_beijing=False)
            orch.plan = plan

    await db.flush()
    return {
        "code": 200,
        "message": "success",
        "data": {"status": "delayed", "scheduled_at": utc_to_beijing_iso(task.scheduled_at)},
    }


@router.post("/tasks/{task_id}/run-now")
async def run_now_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(ScheduleTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("pending", "confirming", "running", "recurring"):
        raise HTTPException(status_code=400, detail=f"Cannot run task in '{task.status}' status")

    if getattr(task, "is_parent", False):
        running_child_result = await db.execute(
            select(ScheduleTask).where(
                ScheduleTask.parent_task_id == task.id,
                ScheduleTask.status == "running",
            )
        )
        if running_child_result.scalars().first() is not None:
            raise HTTPException(status_code=400, detail="当前有子任务正在执行，无法立即执行")

    now = _now_local_naive()
    if task.original_scheduled_at is None:
        task.original_scheduled_at = task.scheduled_at
    task.current_scheduled_at = now
    task.scheduled_at = now
    task.status = "recurring" if bool(getattr(task, "is_parent", False)) else "pending"
    task.confirm_action = "run_now"
    task.confirm_deadline = None
    await db.flush()

    from app.services.sse_manager import sse_manager
    await sse_manager.broadcast("task.status_changed", {"task_id": task.id, "status": "pending"})

    return {
        "code": 200,
        "message": "success",
        "data": {"status": "pending", "scheduled_at": utc_to_beijing_iso(task.scheduled_at)},
    }


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(ScheduleTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "cancelled"
    task.confirm_action = "cancelled"
    task.confirm_deadline = None

    if bool(getattr(task, "is_parent", False)):
        child_result = await db.execute(
            select(ScheduleTask).where(ScheduleTask.parent_task_id == task.id)
        )
        for child in child_result.scalars().all():
            child.status = "cancelled"
            child.confirm_action = "cancelled"
            child.confirm_deadline = None

        if task.orchestration_id:
            from app.api.orchestration import sync_todos_for_orchestration, update_orchestration_status

            if await update_orchestration_status(db, task.orchestration_id, "pending_confirm"):
                await sync_todos_for_orchestration(db, task.orchestration_id)
    else:
        # non-recurring top-level task should also return to orchestration stage
        if not task.parent_task_id and task.orchestration_id:
            from app.api.orchestration import sync_todos_for_orchestration, update_orchestration_status

            if await update_orchestration_status(db, task.orchestration_id, "pending_confirm"):
                await sync_todos_for_orchestration(db, task.orchestration_id)

        parent = await db.get(ScheduleTask, task.parent_task_id) if task.parent_task_id else None
        if parent and parent.recurrence_cron:
            from app.utils.recurrence import get_next_run_time

            now = _now_local_naive()
            base_time = parent.current_scheduled_at or parent.scheduled_at or now
            try:
                next_run = get_next_run_time(parent.recurrence_cron, base_time)
            except Exception:
                from datetime import timedelta
                next_run = now + timedelta(minutes=1)

            parent.current_scheduled_at = next_run
            parent.scheduled_at = next_run
            parent.status = "recurring"

    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "cancelled", "is_parent": bool(getattr(task, "is_parent", False))}}


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(ScheduleTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "pending"
    task.retry_count = 0
    task.error_message = None
    task.started_at = None
    task.completed_at = None
    next_run_at = _now_local_naive()
    if task.original_scheduled_at is None:
        task.original_scheduled_at = task.scheduled_at
    task.current_scheduled_at = next_run_at
    task.scheduled_at = next_run_at
    task.delay_count = int(task.delay_count or 0) + 1
    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "retrying"}}


@router.post("/tasks/{task_id}/pause")
async def pause_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(ScheduleTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "paused"
    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "paused"}}


@router.post("/tasks/{task_id}/resume-task")
async def resume_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(ScheduleTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "pending"
    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "pending"}}
