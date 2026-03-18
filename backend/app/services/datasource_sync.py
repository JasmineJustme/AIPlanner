import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.datasource import DataSource
from app.services.dify_client import dify_client
from loguru import logger


def _normalize_sync_payload(response: object) -> dict:
    if not isinstance(response, dict):
        return {"raw": response}

    data = response.get("data") if isinstance(response.get("data"), dict) else None
    outputs = data.get("outputs") if isinstance(data, dict) else None
    if isinstance(outputs, dict):
        return outputs
    if isinstance(outputs, str):
        text = outputs.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except json.JSONDecodeError:
            return {"text": outputs}

    for key in ("outputs", "result", "answer", "output"):
        value = response.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            return {"text": value}

    return data or response


def _normalize_output_params(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _pick_nested_value(payload: object, path: str) -> object:
    if not path:
        return None
    current: object = payload
    for part in path.split("."):
        key = part.strip()
        if not key:
            return None
        if isinstance(current, dict):
            if key not in current:
                return None
            current = current.get(key)
            continue
        if isinstance(current, list):
            if not key.isdigit():
                return None
            idx = int(key)
            if idx < 0 or idx >= len(current):
                return None
            current = current[idx]
            continue
        return None
    return current


def _extract_configured_outputs(payload: dict, output_params: object) -> dict:
    names = _normalize_output_params(output_params)
    if not names:
        return payload

    extracted: dict = {}
    for name in names:
        value = _pick_nested_value(payload, name)
        if value is None and "." not in name and name in payload:
            value = payload.get(name)
        if value is None:
            continue
        extracted[name] = value

    # Keep prompt generation robust even when configured paths don't match response shape.
    return extracted or payload


async def sync_all_datasources(db: AsyncSession):
    """Sync all enabled datasources and return combined parsed data"""
    result = await db.execute(select(DataSource).where(DataSource.is_enabled == True))
    datasources = result.scalars().all()

    combined_data = {}
    for ds in datasources:
        try:
            ds.last_sync_status = "running"
            await db.flush()

            response = await dify_client.call_agent(
                ds.dify_endpoint,
                ds.dify_api_key,
                ds.input_params if isinstance(ds.input_params, dict) else {},
                timeout=120,
            )
            parsed_response = _normalize_sync_payload(response)
            resolved_response = _extract_configured_outputs(parsed_response, ds.output_params)
            ds.sync_data_cache = resolved_response
            ds.last_sync_at = datetime.now(UTC).replace(tzinfo=None)
            ds.last_sync_status = "success"
            ds.last_sync_error = None
            combined_data[ds.type] = resolved_response
            logger.info(f"Datasource {ds.type} synced successfully")
        except Exception as e:
            ds.last_sync_status = "failed"
            ds.last_sync_error = str(e)
            logger.error(f"Datasource {ds.type} sync failed: {e}")

    await db.flush()
    return combined_data


async def sync_single_datasource(db: AsyncSession, ds_type: str):
    result = await db.execute(select(DataSource).where(DataSource.type == ds_type))
    ds = result.scalar_one_or_none()
    if not ds:
        return None
    try:
        ds.last_sync_status = "running"
        await db.flush()
        response = await dify_client.call_agent(
            ds.dify_endpoint, ds.dify_api_key, {}, timeout=120
        )
        parsed_response = _normalize_sync_payload(response)
        resolved_response = _extract_configured_outputs(parsed_response, ds.output_params)
        ds.sync_data_cache = resolved_response
        ds.last_sync_at = datetime.now(UTC).replace(tzinfo=None)
        ds.last_sync_status = "success"
        ds.last_sync_error = None
        await db.flush()
        return resolved_response
    except Exception as e:
        ds.last_sync_status = "failed"
        ds.last_sync_error = str(e)
        await db.flush()
        return None
