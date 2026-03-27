import json
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import DateTime, Boolean, select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_db
from app.models import (
    Agent,
    Workflow,
    WAgent,
    WAgentVersion,
    DataSource,
    LLMConfig,
    NotificationChannel,
    SystemSetting,
    NotificationPref,
    NotificationGlobalPref,
)

router = APIRouter(prefix="/config", tags=["config-import-export"])

SECTION_MODELS: list[tuple[str, str, type]] = [
    ("agents", "Agent", Agent),
    ("workflows", "工作流", Workflow),
    ("wagents", "W-Agent", WAgent),
    ("wagent_versions", "W-Agent 版本", WAgentVersion),
    ("datasources", "数据源", DataSource),
    ("llm_configs", "LLM 配置", LLMConfig),
    ("notification_channels", "通知渠道", NotificationChannel),
    ("system_settings", "系统设置", SystemSetting),
    ("notification_prefs", "通知偏好", NotificationPref),
    ("notification_global_prefs", "全局通知偏好", NotificationGlobalPref),
]


def _to_dict(obj):
    d = {}
    for c in obj.__table__.columns:
        val = getattr(obj, c.key)
        if isinstance(val, datetime):
            val = val.isoformat()
        d[c.key] = val
    return d


def _col_names(model):
    return {c.key for c in model.__table__.columns}


def _pk_name(model) -> str:
    for c in model.__table__.columns:
        if c.primary_key:
            return c.key
    return "id"


def _datetime_cols(model) -> set[str]:
    return {c.key for c in model.__table__.columns if isinstance(c.type, DateTime)}


def _boolean_cols(model) -> set[str]:
    return {c.key for c in model.__table__.columns if isinstance(c.type, Boolean)}


def _coerce_values(item: dict, dt_cols: set[str], bool_cols: set[str]) -> dict:
    """Convert JSON string values back to proper Python types for SQLAlchemy."""
    result = {}
    for k, v in item.items():
        if k in dt_cols:
            if v is None:
                result[k] = None
            elif isinstance(v, str):
                try:
                    result[k] = datetime.fromisoformat(v)
                except ValueError:
                    result[k] = None
            else:
                result[k] = v
        elif k in bool_cols:
            if isinstance(v, bool):
                result[k] = v
            elif isinstance(v, (int, float)):
                result[k] = bool(v)
            elif isinstance(v, str):
                result[k] = v.lower() in ("true", "1", "yes")
            else:
                result[k] = bool(v) if v is not None else False
        else:
            result[k] = v
    return result


@router.get("/export")
async def export_configs(
    db: AsyncSession = Depends(get_db),
):
    data = {}
    for key, _label, model in SECTION_MODELS:
        rows = (await db.execute(select(model))).scalars().all()
        data[key] = [_to_dict(r) for r in rows]
    return {"code": 200, "message": "success", "data": data}


@router.post("/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    try:
        data = json.loads(content.decode("utf-8"))
    except Exception as e:
        return {"code": 400, "message": f"JSON 解析失败: {e}", "data": None}

    if not isinstance(data, dict):
        return {"code": 400, "message": "配置文件格式不正确，应为 JSON 对象", "data": None}

    sections = []
    for key, label, model in SECTION_MODELS:
        file_items = data.get(key, [])
        if not isinstance(file_items, list):
            file_items = []
        file_count = len(file_items)

        existing_rows = (await db.execute(select(model))).scalars().all()
        existing_count = len(existing_rows)

        pk = _pk_name(model)
        existing_ids = {getattr(r, pk) for r in existing_rows}
        file_ids = {item.get(pk) for item in file_items if isinstance(item, dict) and item.get(pk)}

        overlap = file_ids & existing_ids
        new_count = len(file_ids - existing_ids)
        update_count = len(overlap)

        sections.append({
            "key": key,
            "label": label,
            "file_count": file_count,
            "existing_count": existing_count,
            "new_count": new_count,
            "update_count": update_count,
        })

    return {"code": 200, "message": "success", "data": {"sections": sections}}


@router.post("/import")
async def import_configs(
    file: UploadFile = File(...),
    sections: str = Form(""),
    mode: str = Form("merge"),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    try:
        data = json.loads(content.decode("utf-8"))
    except Exception as e:
        return {"code": 400, "message": f"JSON 解析失败: {e}", "data": None}

    if not isinstance(data, dict):
        return {"code": 400, "message": "配置文件格式不正确", "data": None}

    selected_sections: set[str] | None = None
    if sections.strip():
        selected_sections = {s.strip() for s in sections.split(",") if s.strip()}

    result = {}
    errors = []

    for key, label, model in SECTION_MODELS:
        if selected_sections is not None and key not in selected_sections:
            continue

        items = data.get(key, [])
        if not isinstance(items, list) or not items:
            result[key] = {"added": 0, "updated": 0, "skipped": 0}
            continue

        cols = _col_names(model)
        pk = _pk_name(model)
        dt_cols = _datetime_cols(model)
        bool_cols = _boolean_cols(model)
        added = 0
        updated = 0
        skipped = 0

        if mode == "replace":
            existing = (await db.execute(select(model))).scalars().all()
            for row in existing:
                await db.delete(row)
            await db.flush()

            for item in items:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                filtered = {k: v for k, v in item.items() if k in cols}
                if not filtered:
                    skipped += 1
                    continue
                filtered = _coerce_values(filtered, dt_cols, bool_cols)
                try:
                    obj = model(**filtered)
                    db.add(obj)
                    added += 1
                except Exception as e:
                    logger.warning(f"Import replace error in {key}: {e}")
                    skipped += 1
            try:
                await db.flush()
            except Exception as e:
                logger.error(f"Import flush error in {key} (replace): {e}")
                await db.rollback()
                errors.append({"section": key, "error": str(e)})
        else:
            for item in items:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                filtered = {k: v for k, v in item.items() if k in cols}
                if not filtered:
                    skipped += 1
                    continue
                filtered = _coerce_values(filtered, dt_cols, bool_cols)

                pk_value = filtered.get(pk)
                if pk_value:
                    existing_obj = await db.get(model, pk_value)
                    if existing_obj:
                        for attr_key, attr_val in filtered.items():
                            if attr_key != pk:
                                setattr(existing_obj, attr_key, attr_val)
                        updated += 1
                        continue

                try:
                    obj = model(**filtered)
                    db.add(obj)
                    added += 1
                except Exception as e:
                    logger.warning(f"Import merge error in {key}: {e}")
                    skipped += 1

            try:
                await db.flush()
            except Exception as e:
                logger.error(f"Import flush error in {key} (merge): {e}")
                await db.rollback()
                errors.append({"section": key, "error": str(e)})

        result[key] = {"added": added, "updated": updated, "skipped": skipped}

    if errors:
        return {"code": 207, "message": "部分导入完成", "data": result, "errors": errors}
    return {"code": 200, "message": "success", "data": result}
