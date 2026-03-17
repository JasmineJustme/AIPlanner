import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import LLMConfig
from app.schemas.llm_config import LLMConfigUpdate, LLMConfigResponse
from app.services.llm_client import llm_client

router = APIRouter(prefix="/config/llm", tags=["config-llm"])

LLM_PURPOSES = ["chat", "extract", "summarize", "todo_analysis", "todo_dedup", "orchestration"]
REQUIRED_PROMPT_PLACEHOLDERS_BY_PURPOSE = {
    "orchestration": [
        "{current_time}",
        "{todo_desc}",
        "{agent_desc}",
        "{wagent_desc}",
        "{workflow_desc}",
    ],
    "todo_analysis": [
        "{current_time}",
        "{datasource_info}",
        "{responsibilities}",
    ],
    "todo_dedup": [
        "{current_time}",
        "{todo_desc}",
    ],
}


def _serialize_llm_config(cfg: LLMConfig) -> LLMConfigResponse:
    data = LLMConfigResponse.model_validate(cfg).model_dump()
    prefs = cfg.user_preferences or {}
    data["temperature_enabled"] = prefs.get("temperature_enabled", True)
    data["top_p_enabled"] = prefs.get("top_p_enabled", True)
    return LLMConfigResponse.model_validate(data)


def _validate_orchestration_prompt_template(purpose: str, prompt_template: str | None) -> None:
    required = REQUIRED_PROMPT_PLACEHOLDERS_BY_PURPOSE.get(purpose)
    if required is None or prompt_template is None:
        return
    missing = [token for token in required if token not in prompt_template]
    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "MISSING_REQUIRED_PLACEHOLDERS",
                "field": "prompt_template",
                "purpose": purpose,
                "missing_placeholders": missing,
                "message": (
                    f"{purpose} prompt_template missing required placeholders: "
                    + ", ".join(missing)
                ),
            },
        )


def _normalize_purpose_alias(purpose: str) -> str:
    return "todo_dedup" if purpose == "scheduling" else purpose


async def _migrate_scheduling_to_todo_dedup_if_needed(db: AsyncSession) -> None:
    # Reuse old "scheduling" config data under the new "todo_dedup" purpose.
    dedup_result = await db.execute(select(LLMConfig).where(LLMConfig.purpose == "todo_dedup"))
    dedup_cfg = dedup_result.scalar_one_or_none()
    scheduling_result = await db.execute(select(LLMConfig).where(LLMConfig.purpose == "scheduling"))
    scheduling_cfg = scheduling_result.scalar_one_or_none()
    if not scheduling_cfg:
        return
    if dedup_cfg:
        await db.delete(scheduling_cfg)
        await db.flush()
        return
    scheduling_cfg.purpose = "todo_dedup"
    await db.flush()


@router.get("")
async def list_llm_configs(
    db: AsyncSession = Depends(get_db),
):
    await _migrate_scheduling_to_todo_dedup_if_needed(db)
    result = await db.execute(select(LLMConfig))
    items = result.scalars().all()
    existing = {c.purpose for c in items}
    for purpose in LLM_PURPOSES:
        if purpose not in existing:
            cfg = LLMConfig(purpose=purpose, prompt_template="")
            db.add(cfg)
            await db.flush()
            items.append(cfg)
    return {
        "code": 200,
        "message": "success",
        "data": [_serialize_llm_config(i) for i in items],
    }


@router.get("/{purpose}")
async def get_llm_config(
    purpose: str,
    db: AsyncSession = Depends(get_db),
):
    purpose = _normalize_purpose_alias(purpose)
    await _migrate_scheduling_to_todo_dedup_if_needed(db)
    result = await db.execute(select(LLMConfig).where(LLMConfig.purpose == purpose))
    cfg = result.scalar_one_or_none()
    if not cfg:
        cfg = LLMConfig(purpose=purpose, prompt_template="")
        db.add(cfg)
        await db.flush()
        await db.refresh(cfg)
    return {"code": 200, "message": "success", "data": _serialize_llm_config(cfg)}


@router.put("/{purpose}")
async def update_llm_config(
    purpose: str,
    payload: LLMConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    purpose = _normalize_purpose_alias(purpose)
    await _migrate_scheduling_to_todo_dedup_if_needed(db)
    result = await db.execute(select(LLMConfig).where(LLMConfig.purpose == purpose))
    cfg = result.scalar_one_or_none()
    if not cfg:
        cfg = LLMConfig(purpose=purpose, prompt_template="")
        db.add(cfg)
        await db.flush()
    data = payload.model_dump(exclude_unset=True)
    _validate_orchestration_prompt_template(purpose, data.get("prompt_template"))

    prefs = dict(cfg.user_preferences or {})
    for pref_key in ("temperature_enabled", "top_p_enabled"):
        if pref_key in data:
            prefs[pref_key] = data.pop(pref_key)
    cfg.user_preferences = prefs

    for k, v in data.items():
        setattr(cfg, k, v)
    await db.flush()
    await db.refresh(cfg)
    return {"code": 200, "message": "success", "data": _serialize_llm_config(cfg)}


@router.post("/{purpose}/test")
async def test_llm_config(
    purpose: str,
    db: AsyncSession = Depends(get_db),
):
    purpose = _normalize_purpose_alias(purpose)
    await _migrate_scheduling_to_todo_dedup_if_needed(db)
    result = await db.execute(select(LLMConfig).where(LLMConfig.purpose == purpose))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="LLM config not found")

    # Check if configured
    if not cfg.api_key or not cfg.api_endpoint:
         # Return specific error so frontend can show helpful message, or handle as 400
         # Using 200 with error structure to match client handling if preferred,
         # but standard HTTP 400 is better for "Bad Request" (unconfigured).
         # However, to be consistent with client error handling which might prefer 200 OK with error body for some logic:
         # let's stick to standard exception which client interceptor handles.
         raise HTTPException(status_code=400, detail="API Key and Endpoint are required")

    start_time = time.time()
    try:
        # Simple test message
        response = await llm_client.chat(cfg, [{"role": "user", "content": "Hello"}])
        latency = int((time.time() - start_time) * 1000)

        return {
            "code": 200,
            "message": "success",
            "data": {
                "connected": True,
                "latency_ms": latency,
                "response": response.get("content", "")[:50] + "..."
            }
        }
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        # Return 200 so frontend can parse the specific error message easily in data
        return {
             "code": 500,
             "message": "failed",
             "data": {
                 "connected": False,
                 "latency_ms": latency,
                 "error": str(e)
             }
        }


@router.get("/{purpose}/usage")
async def get_llm_usage(
    purpose: str,
    db: AsyncSession = Depends(get_db),
):
    purpose = _normalize_purpose_alias(purpose)
    await _migrate_scheduling_to_todo_dedup_if_needed(db)
    result = await db.execute(select(LLMConfig).where(LLMConfig.purpose == purpose))
    cfg = result.scalar_one_or_none()
    if not cfg:
        # Return default zero usage instead of 404
        return {
            "code": 200,
            "message": "success",
            "data": {
                "total_tokens_used": 0,
                "total_cost": 0.0,
                "prompt_version": 1,
            },
        }
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_tokens_used": cfg.total_tokens_used or 0,
            "total_cost": cfg.total_cost or 0.0,
            "prompt_version": cfg.prompt_version or 1,
        },
    }
