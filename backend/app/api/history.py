from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import ExecutionHistory, User
from app.utils.timezone import utc_to_beijing_datetime

router = APIRouter(prefix="/history", tags=["history"])


def _history_scope_filter(current_user: User):
    if getattr(current_user, "is_superuser", False):
        return None
    return ExecutionHistory.user_id == current_user.id


@router.get("/export")
async def export_history(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {"code": 200, "message": "success", "data": {"url": "/exports/history.csv"}}


@router.get("")
async def list_execution_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    agent_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    offset = (page - 1) * size
    q = select(ExecutionHistory)
    count_q = select(func.count()).select_from(ExecutionHistory)
    scope_filter = _history_scope_filter(current_user)
    if scope_filter is not None:
        q = q.where(scope_filter)
        count_q = count_q.where(scope_filter)
    if status:
        q = q.where(ExecutionHistory.status == status)
        count_q = count_q.where(ExecutionHistory.status == status)
    if agent_id:
        q = q.where(ExecutionHistory.agent_id == agent_id)
        count_q = count_q.where(ExecutionHistory.agent_id == agent_id)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0
    result = await db.execute(
        q.offset(offset).limit(size).order_by(ExecutionHistory.started_at.desc())
    )
    items = result.scalars().all()
    pages = (total + size - 1) // size if total > 0 else 0
    data = [
        {
            "id": h.id,
            "task_id": h.task_id,
            "agent_id": h.agent_id,
            "wagent_id": h.wagent_id,
            "agent_name": h.agent_name,
            "status": h.status,
            "input_params": h.input_params,
            "started_at": utc_to_beijing_datetime(h.started_at),
            "completed_at": utc_to_beijing_datetime(h.completed_at),
            "duration_ms": h.duration_ms,
        }
        for h in items
    ]
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": data,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        },
    }


@router.get("/{history_id}")
async def get_history_detail(
    history_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(ExecutionHistory).where(ExecutionHistory.id == history_id)
    scope_filter = await _history_scope_filter(current_user)
    if scope_filter is not None:
        q = q.where(scope_filter)
    result = await db.execute(q)
    h = result.scalar_one_or_none()
    if not h:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="History not found")
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": h.id,
            "task_id": h.task_id,
            "agent_id": h.agent_id,
            "wagent_id": h.wagent_id,
            "agent_name": h.agent_name,
            "status": h.status,
            "input_params": h.input_params,
            "output_result": h.output_result,
            "error_message": h.error_message,
            "execution_log": h.execution_log,
            "duration_ms": h.duration_ms,
            "tokens_used": h.tokens_used,
            "started_at": utc_to_beijing_datetime(h.started_at),
            "completed_at": utc_to_beijing_datetime(h.completed_at),
        },
    }
