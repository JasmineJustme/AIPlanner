from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import SystemSetting, NotificationPref, NotificationGlobalPref
from app.schemas.settings import (
    SystemSettingsUpdate,
    NotificationPrefUpdate,
    NotificationGlobalPrefUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _normalize_system_setting_payload(key: str, value: object) -> dict:
    raw = value.get("value") if isinstance(value, dict) and "value" in value else value

    if key == "auto_smart_discovery_enabled":
        return {"value": bool(raw)}

    if key == "auto_smart_discovery_interval_minutes":
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            minutes = 15
        return {"value": max(1, min(minutes, 60))}

    return value if isinstance(value, dict) else {"value": value}


async def _ensure_notification_pref_channel_map_column(db: AsyncSession) -> None:
    bind = db.get_bind()
    if not bind or bind.dialect.name != "sqlite":
        return

    table_info = await db.execute(text("PRAGMA table_info(notification_prefs)"))
    columns = {row[1] for row in table_info.fetchall()}
    if "channel_enabled_map" in columns:
        return

    await db.execute(
        text("ALTER TABLE notification_prefs ADD COLUMN channel_enabled_map JSON NOT NULL DEFAULT '{}'"),
    )
    await db.execute(
        text(
            """
            UPDATE notification_prefs
            SET channel_enabled_map =
                '{"in_app":' || CASE WHEN in_app_enabled THEN 'true' ELSE 'false' END ||
                ',"email_workflow":' || CASE WHEN email_enabled THEN 'true' ELSE 'false' END ||
                ',"wechat_workflow":' || CASE WHEN wechat_enabled THEN 'true' ELSE 'false' END ||
                '}'
            WHERE channel_enabled_map IS NULL OR channel_enabled_map = '{}'
            """
        ),
    )


def _normalize_channel_map(raw: object) -> dict[str, bool]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, bool] = {}
    for key, value in raw.items():
        channel_type = str(key).strip()
        if not channel_type:
            continue
        normalized[channel_type] = bool(value)
    return normalized


def _pref_channel_map(pref: NotificationPref | None) -> dict[str, bool]:
    if not pref:
        return {
            "in_app": True,
            "email_workflow": False,
            "wechat_workflow": False,
        }

    merged = _normalize_channel_map(getattr(pref, "channel_enabled_map", {}))
    merged["in_app"] = True
    merged.setdefault("email_workflow", bool(pref.email_enabled))
    merged.setdefault("wechat_workflow", bool(pref.wechat_enabled))
    return merged


@router.get("")
async def get_settings(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemSetting))
    items = result.scalars().all()
    data = {s.key: s.value for s in items}
    return {"code": 200, "message": "success", "data": data}


@router.put("")
async def update_settings(
    payload: SystemSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    for key, value in payload.settings.items():
        normalized_value = _normalize_system_setting_payload(key, value)
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = normalized_value
        else:
            setting = SystemSetting(key=key, value=normalized_value)
            db.add(setting)
    await db.flush()
    return {"code": 200, "message": "success", "data": None}


@router.get("/notification-prefs")
async def get_notification_prefs(
    db: AsyncSession = Depends(get_db),
):
    await _ensure_notification_pref_channel_map_column(db)
    result = await db.execute(select(NotificationPref))
    items = result.scalars().all()
    data = [
        {
            "message_type": p.message_type,
            "in_app_enabled": p.in_app_enabled,
            "email_enabled": p.email_enabled,
            "wechat_enabled": p.wechat_enabled,
            "channel_enabled_map": _pref_channel_map(p),
        }
        for p in items
    ]
    return {"code": 200, "message": "success", "data": data}


@router.put("/notification-prefs")
async def update_notification_prefs(
    payload: NotificationPrefUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_notification_pref_channel_map_column(db)
    result = await db.execute(
        select(NotificationPref).where(
            NotificationPref.message_type == payload.message_type,
        )
    )
    pref = result.scalar_one_or_none()
    requested_map = _normalize_channel_map(payload.channel_enabled_map)
    merged_map = {
        "in_app": payload.in_app_enabled if payload.in_app_enabled is not None else True,
        "email_workflow": payload.email_enabled if payload.email_enabled is not None else False,
        "wechat_workflow": payload.wechat_enabled if payload.wechat_enabled is not None else False,
    }
    if pref:
        merged_map = _pref_channel_map(pref)

    merged_map.update(requested_map)

    in_app_enabled = True
    email_enabled = bool(
        payload.email_enabled if payload.email_enabled is not None else merged_map.get("email_workflow", False)
    )
    wechat_enabled = bool(
        payload.wechat_enabled if payload.wechat_enabled is not None else merged_map.get("wechat_workflow", False)
    )

    merged_map["in_app"] = True
    merged_map["email_workflow"] = email_enabled
    merged_map["wechat_workflow"] = wechat_enabled

    if pref:
        pref.in_app_enabled = in_app_enabled
        pref.email_enabled = email_enabled
        pref.wechat_enabled = wechat_enabled
        pref.channel_enabled_map = merged_map
    else:
        pref = NotificationPref(
            message_type=payload.message_type,
            in_app_enabled=in_app_enabled,
            email_enabled=email_enabled,
            wechat_enabled=wechat_enabled,
            channel_enabled_map=merged_map,
        )
        db.add(pref)
    await db.flush()
    return {"code": 200, "message": "success", "data": None}


@router.get("/notification-global")
async def get_notification_global(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(NotificationGlobalPref).limit(1))
    pref = result.scalar_one_or_none()
    if not pref:
        return {
            "code": 200,
            "message": "success",
            "data": {
                "dnd_start": None,
                "dnd_end": None,
                "merge_strategy": "none",
                "merge_window_minutes": 5,
                "deadline_advance_minutes": 60,
            },
        }
    return {
        "code": 200,
        "message": "success",
        "data": {
            "dnd_start": pref.dnd_start,
            "dnd_end": pref.dnd_end,
            "merge_strategy": pref.merge_strategy,
            "merge_window_minutes": pref.merge_window_minutes,
            "deadline_advance_minutes": pref.deadline_advance_minutes,
        },
    }


@router.put("/notification-global")
async def update_notification_global(
    payload: NotificationGlobalPrefUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(NotificationGlobalPref).limit(1))
    pref = result.scalar_one_or_none()
    if pref:
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(pref, k, v)
    else:
        pref = NotificationGlobalPref(**payload.model_dump())
        db.add(pref)
    await db.flush()
    return {"code": 200, "message": "success", "data": None}
