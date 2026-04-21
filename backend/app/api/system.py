from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import SystemSetting
from app.dependencies.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/system", tags=["system"])

INIT_KEY = "system_initialized"


@router.get("/init-status")
async def get_init_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == INIT_KEY))
    setting = result.scalar_one_or_none()
    initialized = setting and setting.value.get("initialized", False) if setting else False
    return {"code": 200, "message": "success", "data": {"initialized": bool(initialized)}}


@router.post("/init-complete")
async def mark_init_complete(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == INIT_KEY))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = {"initialized": True}
    else:
        setting = SystemSetting(key=INIT_KEY, value={"initialized": True})
        db.add(setting)
    await db.flush()
    return {"code": 200, "message": "success", "data": {"initialized": True}}
