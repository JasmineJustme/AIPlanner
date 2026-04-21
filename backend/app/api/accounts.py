import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_admin_user, get_current_user
from app.models.user import AuthSession, OrgUnit, User
from app.schemas.user import (
    AdminLoginResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    OrgUnitCreate,
    OrgUnitResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.security import (
    generate_access_token,
    hash_password,
    hash_token,
    token_expire_time,
    verify_password,
)
from app.utils.timezone import utc_now_naive

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("/login")
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    logger.info("[login] start email={} type={}", payload.email, payload.login_type)
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    password_ok = verify_password(payload.password, user.password_hash)
    if not password_ok:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已禁用")
    if payload.login_type == "admin" and not (user.role == "admin" or user.is_superuser):
        raise HTTPException(status_code=403, detail="该账号不是管理员账号")

    token = generate_access_token()
    expires_at = token_expire_time()
    now = utc_now_naive()
    session = AuthSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=expires_at,
        revoked_at=None,
        last_seen_at=now,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        created_at=now,
    )
    user.last_login_at = now
    db.add(session)
    await db.flush()
    response_cls = AdminLoginResponse if payload.login_type == "admin" else LoginResponse
    return {"code": 200, "message": "success", "data": response_cls(access_token=token, expires_at=expires_at)}


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = utc_now_naive()
    result = await db.execute(select(AuthSession).where(AuthSession.user_id == current_user.id))
    sessions = result.scalars().all()
    for session in sessions:
        if session.revoked_at is None and session.expires_at > now:
            session.revoked_at = now
    await db.flush()
    return {"code": 200, "message": "success", "data": None}


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    data = MeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        org_unit_id=current_user.org_unit_id,
        manager_id=current_user.manager_id,
        is_superuser=current_user.is_superuser,
        is_active=current_user.is_active,
    )
    return {"code": 200, "message": "success", "data": data}


@router.get("/users")
async def list_users(_: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    rows = result.scalars().all()
    return {"code": 200, "message": "success", "data": [UserResponse.model_validate(row) for row in rows]}


@router.post("/users")
async def create_user(payload: UserCreate, _: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    if payload.email:
        email_exists = await db.execute(select(User).where(User.email == payload.email))
        if email_exists.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="邮箱已存在")

    if not payload.org_unit_id:
        raise HTTPException(status_code=400, detail="所有员工账号必须绑定组织单元")

    if payload.role == "member" and payload.manager_id:
        manager_result = await db.execute(select(User).where(User.id == payload.manager_id))
        manager = manager_result.scalar_one_or_none()
        if not manager:
            raise HTTPException(status_code=400, detail="主管账号不存在")
        if manager.org_unit_id != payload.org_unit_id:
            raise HTTPException(status_code=400, detail="主管账号必须属于当前组织单元")

    unit_result = await db.execute(select(OrgUnit).where(OrgUnit.id == payload.org_unit_id))
    org_unit = unit_result.scalar_one_or_none()
    if not org_unit:
        raise HTTPException(status_code=400, detail="组织单元不存在")

    if payload.manager_id:
        manager_result = await db.execute(select(User).where(User.id == payload.manager_id))
        manager = manager_result.scalar_one_or_none()
        if not manager:
            raise HTTPException(status_code=400, detail="主管账号不存在")
        if manager.org_unit_id != payload.org_unit_id:
            raise HTTPException(status_code=400, detail="主管账号必须属于当前组织单元")

    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        org_unit_id=payload.org_unit_id,
        manager_id=payload.manager_id,
        is_active=payload.is_active,
        is_superuser=payload.is_superuser,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return {"code": 200, "message": "success", "data": UserResponse.model_validate(user)}


@router.put("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, _: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    data = payload.model_dump(exclude_unset=True)
    if data.get("email"):
        email_exists = await db.execute(select(User).where(User.email == data["email"], User.id != user_id))
        if email_exists.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="邮箱已存在")
    if data.get("password"):
        user.password_hash = hash_password(data.pop("password"))

    if "org_unit_id" in data or "manager_id" in data or "role" in data:
        new_org_unit_id = data.get("org_unit_id", user.org_unit_id)
        new_manager_id = data.get("manager_id", user.manager_id)
        new_role = data.get("role", user.role)
        if new_role == "member" and new_manager_id:
            manager_result = await db.execute(select(User).where(User.id == new_manager_id))
            manager = manager_result.scalar_one_or_none()
            if not manager:
                raise HTTPException(status_code=400, detail="主管账号不存在")
            if manager.org_unit_id != new_org_unit_id:
                raise HTTPException(status_code=400, detail="主管账号必须属于当前组织单元")

    for key, value in data.items():
        setattr(user, key, value)

    await db.flush()
    await db.refresh(user)
    return {"code": 200, "message": "success", "data": UserResponse.model_validate(user)}


@router.delete("/users/{user_id}")
async def disable_user(user_id: str, _: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_active = False
    await db.flush()
    return {"code": 200, "message": "success", "data": None}


@router.get("/org-units")
async def list_org_units(_: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OrgUnit).order_by(OrgUnit.created_at.asc()))
    rows = result.scalars().all()
    return {"code": 200, "message": "success", "data": [OrgUnitResponse.model_validate(row) for row in rows]}


@router.post("/org-units")
async def create_org_unit(payload: OrgUnitCreate, _: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    if payload.unit_type == "section" and not payload.parent_id:
        raise HTTPException(status_code=400, detail="section 类型部门必须指定 parent_id")
    if payload.unit_type == "department" and payload.parent_id:
        raise HTTPException(status_code=400, detail="department 类型部门不能指定 parent_id")
    if payload.parent_id:
        parent_result = await db.execute(select(OrgUnit).where(OrgUnit.id == payload.parent_id))
        parent = parent_result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=400, detail="父部门不存在")
        if payload.unit_type == "section" and parent.unit_type != "department":
            raise HTTPException(status_code=400, detail="section 的父级必须是 department")

    unit = OrgUnit(**payload.model_dump())
    db.add(unit)
    await db.flush()
    await db.refresh(unit)
    return {"code": 200, "message": "success", "data": OrgUnitResponse.model_validate(unit)}


@router.delete("/org-units/{unit_id}")
async def delete_org_unit(unit_id: str, _: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OrgUnit).where(OrgUnit.id == unit_id))
    unit = result.scalar_one_or_none()
    if not unit:
        raise HTTPException(status_code=404, detail="组织单元不存在")

    descendant_ids: list[str] = []
    queue = [unit.id]
    while queue:
        current_parent_id = queue.pop(0)
        child_result = await db.execute(select(OrgUnit).where(OrgUnit.parent_id == current_parent_id))
        children = child_result.scalars().all()
        for child in children:
            descendant_ids.append(child.id)
            queue.append(child.id)

    if descendant_ids:
        await db.execute(delete(OrgUnit).where(OrgUnit.id.in_(descendant_ids)))

    await db.delete(unit)
    await db.flush()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "deleted_id": unit_id,
            "deleted_child_count": len(descendant_ids),
        },
    }
