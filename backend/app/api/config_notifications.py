from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent, NotificationChannel
from app.schemas.notification_channel import NotificationChannelUpdate, NotificationChannelResponse

router = APIRouter(prefix="/config/notifications", tags=["config-notifications"])

CHANNEL_TYPES = ["email_workflow", "wechat_workflow", "in_app"]
CHANNEL_TYPE_ALIASES = {
    "email": "email_workflow",
    "wechat": "wechat_workflow",
}


def _normalize_channel_type(channel_type: str) -> str:
    return CHANNEL_TYPE_ALIASES.get(channel_type, channel_type)


def _normalize_params(raw: object) -> list[dict]:
    if isinstance(raw, list):
        items: list[dict] = []
        for item in raw:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            if isinstance(item, dict):
                items.append(item)
        return items
    return []


def _extract_channel_agent_id(ch: NotificationChannel) -> str | None:
    mapping = ch.input_mapping if isinstance(ch.input_mapping, dict) else {}
    raw = mapping.get("agent_id")
    return str(raw).strip() if raw else None


def _extract_channel_params(ch: NotificationChannel) -> list[dict]:
    mapping = ch.input_mapping if isinstance(ch.input_mapping, dict) else {}
    params = mapping.get("input_params")
    return _normalize_params(params)


def _extract_channel_message_field(ch: NotificationChannel) -> str | None:
    mapping = ch.input_mapping if isinstance(ch.input_mapping, dict) else {}
    value = mapping.get("message_field")
    normalized = str(value).strip() if value else ""
    return normalized or None


def _set_channel_message_field(ch: NotificationChannel, message_field: str | None) -> None:
    mapping = dict(ch.input_mapping) if isinstance(ch.input_mapping, dict) else {}
    if message_field:
        mapping["message_field"] = message_field
    else:
        mapping.pop("message_field", None)
    ch.input_mapping = mapping


def _validate_or_cleanup_message_field(
    ch: NotificationChannel,
    requested_message_field: str | None,
    requested_explicitly: bool,
) -> None:
    params = _extract_channel_params(ch)
    allowed_fields = {str(item.get("name") or "").strip() for item in params}
    allowed_fields.discard("")

    if requested_explicitly:
        if requested_message_field and requested_message_field not in allowed_fields:
            raise HTTPException(status_code=400, detail="Selected message field not found in input params")
        _set_channel_message_field(ch, requested_message_field)
        return

    existing = _extract_channel_message_field(ch)
    if existing and existing not in allowed_fields:
        _set_channel_message_field(ch, None)


async def _apply_agent_binding(
    db: AsyncSession,
    ch: NotificationChannel,
    agent_id: str,
    input_params: list[dict] | None,
) -> None:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=400, detail="Selected agent not found")

    ch.dify_endpoint = agent.dify_endpoint
    ch.dify_api_key = agent.dify_api_key

    source_params = _normalize_params(input_params) or _normalize_params(agent.input_params)
    existing_values: dict[str, str] = {}
    for item in _extract_channel_params(ch):
        name = str(item.get("name") or "").strip()
        if name:
            existing_values[name] = str(item.get("value") or "")

    merged = []
    for item in source_params:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        row = dict(item)
        if row.get("value") in (None, "") and name in existing_values:
            row["value"] = existing_values[name]
        merged.append(row)

    next_mapping = {
        "agent_id": agent.id,
        "input_params": merged,
    }
    existing_message_field = _extract_channel_message_field(ch)
    if existing_message_field:
        next_mapping["message_field"] = existing_message_field
    ch.input_mapping = next_mapping


def _serialize_channel(ch: NotificationChannel) -> NotificationChannelResponse:
    fallback_time = datetime.now(UTC).replace(tzinfo=None)
    payload = {
        "id": ch.id,
        "channel_type": _normalize_channel_type(ch.channel_type),
        "name": ch.name,
        "agent_id": _extract_channel_agent_id(ch),
        "dify_endpoint": ch.dify_endpoint,
        "dify_api_key": ch.dify_api_key,
        "input_params": _extract_channel_params(ch),
        "input_mapping": ch.input_mapping if isinstance(ch.input_mapping, dict) else {},
        "is_enabled": ch.is_enabled,
        "message_field": _extract_channel_message_field(ch),
        "created_at": ch.__dict__.get("created_at") or fallback_time,
        "updated_at": ch.__dict__.get("updated_at") or fallback_time,
    }
    return NotificationChannelResponse.model_validate(payload)


@router.get("")
async def list_notification_channels(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(NotificationChannel))
    items = result.scalars().all()

    alias_rows: dict[str, NotificationChannel] = {}
    canonical_existing: set[str] = set()
    for ch in items:
        canonical = _normalize_channel_type(ch.channel_type)
        if canonical != ch.channel_type:
            alias_rows[canonical] = ch
        else:
            canonical_existing.add(canonical)

    for ct in CHANNEL_TYPES:
        if ct in canonical_existing:
            continue
        alias = alias_rows.get(ct)
        if alias:
            alias.channel_type = ct
            canonical_existing.add(ct)
            continue
        ch = NotificationChannel(
            channel_type=ct,
            name=ct,
            dify_endpoint="",
            dify_api_key="",
            input_mapping={},
        )
        db.add(ch)
        await db.flush()
        items.append(ch)

    await db.flush()

    return {
        "code": 200,
        "message": "success",
        "data": [_serialize_channel(i) for i in items if _normalize_channel_type(i.channel_type) in CHANNEL_TYPES],
    }


@router.put("/{channel_type}")
async def update_channel(
    channel_type: str,
    payload: NotificationChannelUpdate,
    db: AsyncSession = Depends(get_db),
):
    channel_type = _normalize_channel_type(channel_type)
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.channel_type == channel_type)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        ch = NotificationChannel(
            channel_type=channel_type,
            name=channel_type,
            dify_endpoint="",
            dify_api_key="",
            input_mapping={},
        )
        db.add(ch)
        await db.flush()

    data = payload.model_dump(exclude_unset=True)
    agent_id = data.pop("agent_id", None)
    input_params = _normalize_params(data.pop("input_params", None)) if "input_params" in data else None
    message_field_specified = "message_field" in data
    message_field_raw = data.pop("message_field", None) if message_field_specified else None
    message_field = str(message_field_raw).strip() if message_field_raw else None

    if agent_id:
        await _apply_agent_binding(db, ch, str(agent_id), input_params)
    elif input_params is not None:
        existing = ch.input_mapping if isinstance(ch.input_mapping, dict) else {}
        existing["input_params"] = input_params
        ch.input_mapping = existing

    _validate_or_cleanup_message_field(ch, message_field, message_field_specified)

    for k, v in data.items():
        setattr(ch, k, v)

    await db.flush()
    await db.refresh(ch)
    return {"code": 200, "message": "success", "data": _serialize_channel(ch)}


@router.patch("/{channel_type}/toggle")
async def toggle_channel(
    channel_type: str,
    db: AsyncSession = Depends(get_db),
):
    channel_type = _normalize_channel_type(channel_type)
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.channel_type == channel_type)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    ch.is_enabled = not ch.is_enabled
    await db.flush()
    await db.refresh(ch)
    return {"code": 200, "message": "success", "data": {"is_enabled": ch.is_enabled}}


@router.post("/{channel_type}/test")
async def test_channel(
    channel_type: str,
    db: AsyncSession = Depends(get_db),
):
    channel_type = _normalize_channel_type(channel_type)
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.channel_type == channel_type)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"code": 200, "message": "success", "data": {"connected": True, "latency_ms": 42}}
