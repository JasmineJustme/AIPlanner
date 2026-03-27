import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.config_datasources import list_datasources, test_datasource as run_datasource_test, update_datasource
from app.models.agent import Agent
from app.models.base import Base
from app.models.datasource import DataSource
from app.schemas.datasource import DataSourceUpdate


@pytest.mark.asyncio
async def test_update_datasource_persists_agent_id_and_copies_agent_fields():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Agent.__table__, DataSource.__table__])

    try:
        async with session_factory() as db:
            agent = Agent(
                name="mail-agent",
                description="",
                capability_tags=[],
                dify_endpoint="https://example.com/dify",
                dify_api_key="agent-key",
                input_params=[{"name": "q", "type": "string"}],
                output_params=[{"name": "answer", "type": "string"}],
            )
            db.add(agent)
            await db.flush()

            await update_datasource(
                "email",
                DataSourceUpdate(name="email datasource", agent_id=agent.id),
                db,
            )
            await db.commit()

            row_result = await db.execute(
                DataSource.__table__.select().where(DataSource.type == "email")
            )
            row = row_result.first()
            assert row is not None
            assert row.agent_id == agent.id
            assert row.dify_endpoint == "https://example.com/dify"
            assert row.dify_api_key == "agent-key"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_datasources_tolerates_legacy_non_list_params():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[DataSource.__table__])

    try:
        async with session_factory() as db:
            ds = DataSource(
                type="legacy",
                name="legacy",
                dify_endpoint="https://legacy.example.com",
                dify_api_key="legacy",
                input_params={"bad": "shape"},
                output_params={"bad": "shape"},
            )
            db.add(ds)
            await db.flush()

            result = await list_datasources(db)
            assert result["code"] == 200
            data = result["data"]
            assert len(data) == 1
            assert data[0].input_params == []
            assert data[0].output_params == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_test_datasource_returns_latency_and_status_on_success(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[DataSource.__table__])

    async def fake_test_connection(endpoint: str, api_key: str):
        assert endpoint == "https://example.com/v1/workflows/run"
        assert api_key == "k"
        return {"connected": True, "status_code": 200, "error": None}

    monkeypatch.setattr("app.api.config_datasources.dify_client.test_connection", fake_test_connection)

    try:
        async with session_factory() as db:
            ds = DataSource(
                type="email",
                name="email",
                dify_endpoint="https://example.com/v1/workflows/run",
                dify_api_key="k",
                input_params=[],
                output_params=[],
            )
            db.add(ds)
            await db.flush()

            result = await run_datasource_test("email", db)
            assert result["code"] == 200
            assert result["data"]["connected"] is True
            assert result["data"]["status_code"] == 200
            assert isinstance(result["data"]["latency_ms"], int)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_test_datasource_raises_502_on_connectivity_failure(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[DataSource.__table__])

    async def fake_test_connection(endpoint: str, api_key: str):
        return {"connected": False, "status_code": 401, "error": "bad key"}

    monkeypatch.setattr("app.api.config_datasources.dify_client.test_connection", fake_test_connection)

    try:
        async with session_factory() as db:
            ds = DataSource(
                type="calendar",
                name="calendar",
                dify_endpoint="https://example.com/v1/workflows/run",
                dify_api_key="k",
                input_params=[],
                output_params=[],
            )
            db.add(ds)
            await db.flush()

            with pytest.raises(HTTPException) as exc:
                await run_datasource_test("calendar", db)
            assert exc.value.status_code == 502
            assert exc.value.detail == "bad key"
    finally:
        await engine.dispose()
