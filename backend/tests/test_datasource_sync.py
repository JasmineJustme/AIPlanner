import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.datasource import DataSource
from app.services.datasource_sync import _normalize_sync_payload, sync_all_datasources


def test_normalize_sync_payload_prefers_dify_outputs():
    payload = {
        "data": {
            "status": "succeeded",
            "outputs": {"events": [{"title": "会议"}]},
        }
    }

    normalized = _normalize_sync_payload(payload)

    assert normalized == {"events": [{"title": "会议"}]}


@pytest.mark.asyncio
async def test_sync_all_datasources_parses_string_outputs(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[DataSource.__table__])

    async def fake_call_agent(_endpoint, _api_key, _inputs, timeout=120):
        assert timeout == 120
        return {
            "data": {
                "status": "succeeded",
                "outputs": '{"todos": [{"todo_summary": "处理报销"}]}'
            }
        }

    monkeypatch.setattr("app.services.datasource_sync.dify_client.call_agent", fake_call_agent)

    try:
        async with session_factory() as db:
            db.add(
                DataSource(
                    type="oa",
                    name="OA",
                    dify_endpoint="https://example.com/v1/workflows/run",
                    dify_api_key="secret",
                    is_enabled=True,
                )
            )
            await db.commit()

            combined = await sync_all_datasources(db)
            await db.commit()

            ds = (await db.execute(__import__("sqlalchemy").select(DataSource))).scalar_one()

        assert combined["oa"] == {"todos": [{"todo_summary": "处理报销"}]}
        assert ds.sync_data_cache == {"todos": [{"todo_summary": "处理报销"}]}
        assert ds.last_sync_status == "success"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sync_all_datasources_extracts_configured_output_params(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[DataSource.__table__])

    async def fake_call_agent(_endpoint, _api_key, _inputs, timeout=120):
        assert timeout == 120
        return {
            "data": {
                "outputs": {
                    "todos": [{"todo_summary": "处理报销"}],
                    "meta": {"source": "mail"},
                }
            }
        }

    monkeypatch.setattr("app.services.datasource_sync.dify_client.call_agent", fake_call_agent)

    try:
        async with session_factory() as db:
            db.add(
                DataSource(
                    type="oa",
                    name="OA",
                    dify_endpoint="https://example.com/v1/workflows/run",
                    dify_api_key="secret",
                    output_params=[{"name": "todos", "type": "array"}],
                    is_enabled=True,
                )
            )
            await db.commit()

            combined = await sync_all_datasources(db)
            await db.commit()

            ds = (await db.execute(__import__("sqlalchemy").select(DataSource))).scalar_one()

        assert combined["oa"] == {"todos": [{"todo_summary": "处理报销"}]}
        assert ds.sync_data_cache == {"todos": [{"todo_summary": "处理报销"}]}
    finally:
        await engine.dispose()


