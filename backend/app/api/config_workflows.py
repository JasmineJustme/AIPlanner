from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Workflow
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowResponse

router = APIRouter(prefix="/config/workflows", tags=["config-workflows"])


@router.get("")
async def list_workflows(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size
    count_result = await db.execute(select(func.count()).select_from(Workflow))
    total = count_result.scalar() or 0
    result = await db.execute(
        select(Workflow).offset(offset).limit(size).order_by(Workflow.created_at.desc())
    )
    items = result.scalars().all()
    pages = (total + size - 1) // size if total > 0 else 0
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [WorkflowResponse.model_validate(i) for i in items],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        },
    }


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"code": 200, "message": "success", "data": WorkflowResponse.model_validate(workflow)}


@router.post("")
async def create_workflow(
    payload: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump()
    workflow = Workflow(
        name=data["name"],
        description=data.get("description"),
        capability_tags=data.get("capability_tags", []),
        dify_endpoint=data["dify_endpoint"],
        dify_api_key=data["dify_api_key"],
        input_params=data.get("input_params", []),
        output_params=data.get("output_params", []),
        timeout_seconds=data.get("timeout_seconds", 300),
    )
    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)
    return {"code": 200, "message": "success", "data": WorkflowResponse.model_validate(workflow)}


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    payload: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(workflow, k, v)
    await db.flush()
    await db.refresh(workflow)
    return {"code": 200, "message": "success", "data": WorkflowResponse.model_validate(workflow)}


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await db.delete(workflow)
    return {"code": 200, "message": "success", "data": None}


@router.patch("/{workflow_id}/toggle")
async def toggle_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    workflow.is_enabled = not workflow.is_enabled
    await db.flush()
    await db.refresh(workflow)
    return {"code": 200, "message": "success", "data": {"is_enabled": workflow.is_enabled}}


@router.post("/{workflow_id}/test")
async def test_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    import time
    from app.services.dify_client import dify_client

    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.dify_endpoint:
        raise HTTPException(status_code=400, detail="Workflow 未配置 Endpoint")

    start = time.monotonic()
    test_result = await dify_client.test_connection(workflow.dify_endpoint, workflow.dify_api_key)
    latency_ms = int((time.monotonic() - start) * 1000)

    if not test_result["connected"]:
        raise HTTPException(status_code=502, detail=test_result["error"])
    return {"code": 200, "message": "success", "data": {"connected": True, "latency_ms": latency_ms}}
