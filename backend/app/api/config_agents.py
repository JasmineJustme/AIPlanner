from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent
from app.schemas.agent import AgentCreate, AgentUpdate, AgentResponse

router = APIRouter(prefix="/config/agents", tags=["config-agents"])


class FetchDifyInfoRequest(BaseModel):
    dify_endpoint: str
    dify_api_key: str


@router.post("/fetch-dify-info")
async def fetch_dify_info(payload: FetchDifyInfoRequest):
    from app.services.dify_client import dify_client

    if not payload.dify_endpoint or not payload.dify_api_key:
        raise HTTPException(status_code=400, detail="请提供 Dify 端点和 API Key")

    meta = await dify_client.fetch_app_meta(payload.dify_endpoint, payload.dify_api_key)
    return {"code": 200, "message": "success", "data": meta}


@router.get("")
async def list_agents(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size
    count_result = await db.execute(select(func.count()).select_from(Agent))
    total = count_result.scalar() or 0
    result = await db.execute(
        select(Agent).offset(offset).limit(size).order_by(Agent.created_at.desc())
    )
    items = result.scalars().all()
    pages = (total + size - 1) // size if total > 0 else 0
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [AgentResponse.model_validate(i) for i in items],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        },
    }


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"code": 200, "message": "success", "data": AgentResponse.model_validate(agent)}


@router.post("")
async def create_agent(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump()
    agent = Agent(
        name=data["name"],
        description=data.get("description"),
        capability_tags=data.get("capability_tags", []),
        dify_endpoint=data["dify_endpoint"],
        dify_api_key=data["dify_api_key"],
        input_params=data.get("input_params", []),
        output_params=data.get("output_params", []),
        timeout_seconds=data.get("timeout_seconds", 300),
        auto_execute=data.get("auto_execute", False),
        confirm_before_exec=data.get("confirm_before_exec", True),
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return {"code": 200, "message": "success", "data": AgentResponse.model_validate(agent)}


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k in ("input_params", "output_params") and v is not None:
            v = [p.model_dump() if hasattr(p, "model_dump") else p for p in v]
        setattr(agent, k, v)
    await db.flush()
    await db.refresh(agent)
    return {"code": 200, "message": "success", "data": AgentResponse.model_validate(agent)}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    return {"code": 200, "message": "success", "data": None}


@router.patch("/{agent_id}/toggle")
async def toggle_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.is_enabled = not agent.is_enabled
    await db.flush()
    await db.refresh(agent)
    return {"code": 200, "message": "success", "data": {"is_enabled": agent.is_enabled}}


@router.post("/{agent_id}/test")
async def test_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    import time
    from app.services.dify_client import dify_client

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent.dify_endpoint:
        raise HTTPException(status_code=400, detail="Agent 未配置 Endpoint")

    start = time.monotonic()
    test_result = await dify_client.test_connection(agent.dify_endpoint, agent.dify_api_key)
    latency_ms = int((time.monotonic() - start) * 1000)

    if not test_result["connected"]:
        raise HTTPException(status_code=502, detail=test_result["error"])
    return {"code": 200, "message": "success", "data": {"connected": True, "latency_ms": latency_ms}}
