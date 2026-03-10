from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ScheduleTask, SchedulePlan, Agent, WAgent

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


def _task_to_dict(t: ScheduleTask, agent_name: str | None = None, plan_name: str | None = None) -> dict:
    return {
        "id": t.id,
        "plan_id": t.plan_id,
        "plan_name": plan_name,
        "orchestration_id": t.orchestration_id,
        "agent_id": t.agent_id,
        "wagent_id": t.wagent_id,
        "agent_name": agent_name,
        "wagent_version": t.wagent_version,
        "status": t.status,
        "priority": t.priority,
        "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "input_params": t.input_params,
        "output_result": t.output_result,
        "error_message": t.error_message,
        "retry_count": t.retry_count,
        "max_retries": t.max_retries,
        "dependencies": t.dependencies or [],
        "execution_log": t.execution_log,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
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
            "next_run_at": p.next_run_at.isoformat() if p.next_run_at else None,
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
    q = select(ScheduleTask).order_by(ScheduleTask.scheduled_at.desc())
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
    return {"code": 200, "message": "success", "data": _task_to_dict(t, agent_name=agent_name, plan_name=plan_name)}


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
    plan.status = "cancelled"
    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "cancelled"}}


@router.get("/gantt")
async def get_gantt_data(
    plan_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(ScheduleTask).where(ScheduleTask.status != "cancelled").order_by(ScheduleTask.scheduled_at)
    if plan_id:
        q = q.where(ScheduleTask.plan_id == plan_id)
    result = await db.execute(q)
    items = result.scalars().all()

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

    tasks = []
    for t in items:
        name = agents_map.get(t.agent_id or t.wagent_id or "", f"Task {t.id[:8]}")
        start = t.scheduled_at
        end = t.completed_at or t.started_at or t.scheduled_at
        if end == start and start:
            from datetime import timedelta
            end = start + timedelta(hours=1)
        tasks.append({
            "id": t.id,
            "name": name,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
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
    task.status = "pending"
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
    from datetime import datetime, timedelta
    task = await db.get(ScheduleTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    minutes = payload.get("minutes", 30)
    task.scheduled_at = datetime.utcnow() + timedelta(minutes=minutes)
    task.status = "pending"
    task.confirm_action = "delayed"
    task.confirm_deadline = None
    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "delayed"}}


@router.post("/tasks/{task_id}/skip")
async def skip_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(ScheduleTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "skipped"
    task.confirm_action = "skipped"
    task.confirm_deadline = None
    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "skipped"}}


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

    # Update associated items if possible
    if task.orchestration_id:
        from app.api.orchestration import update_orchestration_status
        # Revert orchestration to pending_confirm
        update_orchestration_status(task.orchestration_id, "pending_confirm")

        # Also find related Todos and update them to pending_confirm?
        # Todos have orchestration_id. Update all todos with this orchestration_id.
        from app.models import Todo
        result = await db.execute(select(Todo).where(Todo.orchestration_id == task.orchestration_id))
        todos = result.scalars().all()
        for t in todos:
            # status "pending_confirm" to match orchestration status
            t.status = "pending_confirm"

    await db.flush()
    return {"code": 200, "message": "success", "data": {"status": "cancelled"}}


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
    from datetime import datetime
    task.scheduled_at = datetime.utcnow()
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
