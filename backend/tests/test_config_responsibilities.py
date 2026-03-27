import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.config_responsibilities import (
    create_responsibility,
    delete_responsibility,
    list_responsibilities,
)
from app.models.base import Base
from app.models.responsibility import Responsibility
from app.schemas.responsibility import ResponsibilityCreate


@pytest.mark.asyncio
async def test_responsibility_tree_create_and_delete():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Responsibility.__table__])

    try:
        async with session_factory() as db:
            root_res = await create_responsibility(
                ResponsibilityCreate(
                    title="研发管理",
                    description="负责研发管理工作",
                ),
                db,
            )
            root = root_res["data"]

            await create_responsibility(
                ResponsibilityCreate(
                    parent_id=root.id,
                    title="编写PRD文档",
                    description="负责需求文档产出",
                ),
                db,
            )
            await db.flush()

            tree_res = await list_responsibilities(db)
            assert tree_res["code"] == 200
            assert len(tree_res["data"]) == 1
            assert tree_res["data"][0].title == "研发管理"
            assert len(tree_res["data"][0].children) == 1

            await delete_responsibility(root.id, db)
            await db.flush()
            tree_after = await list_responsibilities(db)
            assert tree_after["data"] == []
    finally:
        await engine.dispose()

