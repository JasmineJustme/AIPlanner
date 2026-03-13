from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import time

from app.database import get_db
from app.models import Agent, DataSource
from app.schemas.datasource import DataSourceCreate, DataSourceUpdate, DataSourceResponse
from app.services.dify_client import dify_client

router = APIRouter(prefix="/config/datasources", tags=["config-datasources"])


def _normalize_params(raw: object) -> list[dict]:
    if isinstance(raw, list):
        normalized: list[dict] = []
        for item in raw:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            if isinstance(item, dict):
                normalized.append(item)
        return normalized
    return []


async def _apply_agent_binding(
    db: AsyncSession,
    ds: DataSource,
    agent_id: str | None,
) -> None:
    if not agent_id:
        ds.agent_id = None
        return
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=400, detail="Selected agent not found")
    ds.agent_id = agent.id
    ds.dify_endpoint = agent.dify_endpoint
    ds.dify_api_key = agent.dify_api_key
    ds.input_params = _normalize_params(agent.input_params)
    ds.output_params = _normalize_params(agent.output_params)


def _serialize_datasource(ds: DataSource) -> DataSourceResponse:
    payload = {
        "id": ds.id,
        "name": ds.name,
        "type": ds.type,
        "agent_id": ds.agent_id,
        "dify_endpoint": ds.dify_endpoint,
        "dify_api_key": ds.dify_api_key,
        "input_params": _normalize_params(ds.input_params),
        "output_params": _normalize_params(ds.output_params),
        "is_enabled": ds.is_enabled,
        "last_sync_at": ds.last_sync_at,
        "last_sync_status": ds.last_sync_status,
        "last_sync_error": ds.last_sync_error,
        "created_at": ds.created_at,
        "updated_at": ds.updated_at,
    }
    return DataSourceResponse.model_validate(payload)


def _mark_datasource_check(ds: DataSource, status: str, error: str | None = None) -> None:
    ds.last_sync_at = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    ds.last_sync_status = status
    ds.last_sync_error = error


@router.get("")
async def list_datasources(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DataSource))
    items = result.scalars().all()
    return {
        "code": 200,
        "message": "success",
        "data": [_serialize_datasource(i) for i in items],
    }


@router.post("")
async def create_datasource(
    payload: DataSourceCreate,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(DataSource).where(DataSource.type == payload.type))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"数据源类型 '{payload.type}' 已存在")
    ds = DataSource(
        type=payload.type,
        name=payload.name,
        agent_id=None,
        dify_endpoint=payload.dify_endpoint or "",
        dify_api_key=payload.dify_api_key or "",
        input_params=([p.model_dump() for p in payload.input_params] if payload.input_params else []),
        output_params=([p.model_dump() for p in payload.output_params] if payload.output_params else []),
    )
    db.add(ds)
    if payload.agent_id:
        await _apply_agent_binding(db, ds, payload.agent_id)
    await db.flush()
    await db.refresh(ds)
    return {
        "code": 200,
        "message": "success",
        "data": _serialize_datasource(ds),
    }


@router.put("/{ds_type}")
async def update_datasource(
    ds_type: str,
    payload: DataSourceUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DataSource).where(DataSource.type == ds_type))
    ds = result.scalar_one_or_none()
    if not ds:
        ds = DataSource(type=ds_type, name=ds_type, dify_endpoint="", dify_api_key="", input_params=[], output_params=[])
        db.add(ds)
        await db.flush()
    data = payload.model_dump(exclude_unset=True)

    # Explicit agent binding has priority and is persisted directly.
    if "agent_id" in data:
        await _apply_agent_binding(db, ds, data.pop("agent_id"))

    if "input_params" in data:
        data["input_params"] = _normalize_params(data["input_params"])
    if "output_params" in data:
        data["output_params"] = _normalize_params(data["output_params"])

    for k, v in data.items():
        setattr(ds, k, v)
    await db.flush()
    await db.refresh(ds)
    return {"code": 200, "message": "success", "data": _serialize_datasource(ds)}


@router.patch("/{ds_type}/toggle")
async def toggle_datasource(
    ds_type: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DataSource).where(DataSource.type == ds_type))
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")
    ds.is_enabled = not ds.is_enabled
    await db.flush()
    await db.refresh(ds)
    return {"code": 200, "message": "success", "data": {"is_enabled": ds.is_enabled}}


@router.post("/{ds_type}/test")
async def test_datasource(
    ds_type: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DataSource).where(DataSource.type == ds_type))
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")
    if not ds.dify_endpoint:
        _mark_datasource_check(ds, "failed", "Datasource 未配置 Endpoint")
        await db.flush()
        raise HTTPException(status_code=400, detail="Datasource 未配置 Endpoint")

    start = time.monotonic()
    test_result = await dify_client.test_connection(ds.dify_endpoint, ds.dify_api_key or "")
    latency_ms = int((time.monotonic() - start) * 1000)

    if not test_result.get("connected"):
        error = test_result.get("error") or "连接失败"
        _mark_datasource_check(ds, "failed", error)
        await db.flush()
        raise HTTPException(status_code=502, detail=error)

    _mark_datasource_check(ds, "success", None)
    await db.flush()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "connected": True,
            "latency_ms": latency_ms,
            "status_code": test_result.get("status_code"),
        },
    }


@router.post("/{ds_type}/sync")
async def sync_datasource(
    ds_type: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DataSource).where(DataSource.type == ds_type))
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")

    _mark_datasource_check(ds, "success", None)
    await db.flush()
    return {"code": 200, "message": "success", "data": "sync triggered"}


@router.delete("/{ds_type}")
async def delete_datasource(
    ds_type: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DataSource).where(DataSource.type == ds_type))
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")
    await db.delete(ds)
    await db.flush()
    return {"code": 200, "message": "success", "data": None}
