import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataSource, SystemSetting
from app.services.dify_client import dify_client
from loguru import logger


async def _get_system_dify_endpoint(db: AsyncSession) -> str:
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == "dify_endpoint"))
    setting = result.scalar_one_or_none()
    raw = setting.value if setting else None
    if isinstance(raw, dict):
        return str(raw.get("value") or raw.get("endpoint") or "").strip()
    if raw is not None:
        return str(raw).strip()
    return ""


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


def _build_input_payload(input_params: object, sync_data_cache: object | None = None) -> dict:
    payload: dict = {}
    if isinstance(input_params, dict):
        for key, value in input_params.items():
            if value is None:
                continue
            payload[str(key)] = value
        return payload

    if not isinstance(input_params, list):
        return payload

    cached = sync_data_cache if isinstance(sync_data_cache, dict) else {}
    for item in input_params:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("variable") or "").strip()
        if not name:
            continue
        if name in cached:
            payload[name] = cached.get(name)
            continue
        if "default" in item and item.get("default") is not None:
            payload[name] = item.get("default")
            continue
        if "value" in item and item.get("value") is not None:
            payload[name] = item.get("value")
    return payload


async def sync_all_datasources(db: AsyncSession):
    """Sync all enabled datasources and return combined parsed data"""
    result = await db.execute(select(DataSource).where(DataSource.is_enabled == True))
    datasources = result.scalars().all()

    combined_data = {}
    for ds in datasources:
        try:
            ds.last_sync_status = "running"
            await db.flush()

            endpoint = await _get_system_dify_endpoint(db)
            if not endpoint:
                raise ValueError("系统设置页未配置 dify_endpoint")

            input_payload = _build_input_payload(ds.input_params, ds.sync_data_cache)
            response = await dify_client.call_agent(
                endpoint,
                ds.dify_api_key,
                input_payload,
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
        endpoint = await _get_system_dify_endpoint(db)
        if not endpoint:
            raise ValueError("系统设置页未配置 dify_endpoint")
        input_payload = _build_input_payload(ds.input_params, ds.sync_data_cache)
        response = await dify_client.call_agent(
            endpoint, ds.dify_api_key, input_payload, timeout=120
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
