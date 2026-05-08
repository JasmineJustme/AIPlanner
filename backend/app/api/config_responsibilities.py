from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import Responsibility, User
from app.schemas.responsibility import (
    ResponsibilityCreate,
    ResponsibilityResponse,
    ResponsibilityTreeNode,
    ResponsibilityUpdate,
)

router = APIRouter(prefix="/config/responsibilities", tags=["config-responsibilities"])


def _build_tree(items: list[Responsibility]) -> list[ResponsibilityTreeNode]:
    by_parent: dict[str | None, list[Responsibility]] = {}
    for item in items:
        by_parent.setdefault(item.parent_id, []).append(item)
    for group in by_parent.values():
        group.sort(key=lambda x: (x.sort_order, x.created_at))

    def build_node(item: Responsibility) -> ResponsibilityTreeNode:
        return ResponsibilityTreeNode(
            **ResponsibilityResponse.model_validate(item).model_dump(),
            children=[build_node(child) for child in by_parent.get(item.id, [])],
        )

    roots = by_parent.get(None, [])
    return [build_node(root) for root in roots]


@router.get("")
async def list_responsibilities(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Responsibility).where(Responsibility.user_id == current_user.id))
    items = result.scalars().all()
    return {"code": 200, "message": "success", "data": _build_tree(items)}


@router.post("")
async def create_responsibility(
    payload: ResponsibilityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.parent_id:
        parent = await db.get(Responsibility, payload.parent_id)
        if not parent or parent.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Parent responsibility not found")

    item = Responsibility(
        user_id=current_user.id,
        parent_id=payload.parent_id,
        title=payload.title,
        description=payload.description,
        sort_order=payload.sort_order,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return {"code": 200, "message": "success", "data": ResponsibilityResponse.model_validate(item)}


@router.put("/{item_id}")
async def update_responsibility(
    item_id: str,
    payload: ResponsibilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Responsibility).where(Responsibility.id == item_id, Responsibility.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Responsibility not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(item, key, value)
    await db.flush()
    await db.refresh(item)
    return {"code": 200, "message": "success", "data": ResponsibilityResponse.model_validate(item)}


@router.delete("/{item_id}")
async def delete_responsibility(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Responsibility).where(Responsibility.user_id == current_user.id))
    items = result.scalars().all()
    by_parent: dict[str | None, list[Responsibility]] = {}
    target = None
    for item in items:
        by_parent.setdefault(item.parent_id, []).append(item)
        if item.id == item_id:
            target = item
    if not target:
        raise HTTPException(status_code=404, detail="Responsibility not found")

    to_delete: list[Responsibility] = []

    def collect(node: Responsibility) -> None:
        to_delete.append(node)
        for child in by_parent.get(node.id, []):
            collect(child)

    collect(target)
    for item in reversed(to_delete):
        await db.delete(item)
    await db.flush()
    return {"code": 200, "message": "success", "data": None}
