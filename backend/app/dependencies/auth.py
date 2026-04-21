from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import AuthSession, User
from app.security import hash_token
from app.utils.timezone import utc_now_naive


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise HTTPException(status_code=401, detail="无效的认证头")
    return parts[1]


async def get_current_user(authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)) -> User:
    token = _extract_bearer_token(authorization)
    token_hash = hash_token(token)
    result = await db.execute(select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(AuthSession.token_hash == token_hash))
    row = result.first()
    if not row:
        raise HTTPException(status_code=401, detail="登录状态已失效")
    session, user = row
    now = utc_now_naive()
    if session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(status_code=401, detail="登录状态已过期")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已禁用")
    session.last_seen_at = now
    return user


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin" and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="仅管理员可访问")
    return current_user
