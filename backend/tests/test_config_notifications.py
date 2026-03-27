import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.config_notifications import create_channel, delete_channel, list_notification_channels, update_channel
from app.models.agent import Agent
from app.models.base import Base
from app.models.notification_channel import NotificationChannel
from app.schemas.notification_channel import NotificationChannelUpdate
from app.schemas.notification_channel import NotificationChannelCreate


@pytest.mark.asyncio
async def test_update_channel_with_agent_binding_copies_credentials_and_params():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Agent.__table__, NotificationChannel.__table__])

    try:
        async with session_factory() as db:
            agent = Agent(
                name="notify-agent",
                description="",
                capability_tags=[],
                dify_endpoint="https://example.com/v1/workflows/run",
                dify_api_key="agent-key",
                input_params=[{"name": "subject", "type": "string", "required": True}],
                output_params=[],
            )
            db.add(agent)
            await db.flush()

            result = await update_channel(
                "email_workflow",
                NotificationChannelUpdate(
                    name="邮件渠道",
                    agent_id=agent.id,
                    input_params=[{"name": "subject", "type": "string", "required": True, "value": "{{title}}"}],
                ),
                db,
            )
            await db.commit()

            saved = result["data"]
            assert saved.agent_id == agent.id
            assert saved.dify_endpoint == "https://example.com/v1/workflows/run"
            assert saved.dify_api_key == "agent-key"
            assert len(saved.input_params) == 1
            assert saved.input_params[0].name == "subject"
            assert saved.input_params[0].value == "{{title}}"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_notification_channels_migrates_legacy_channel_type_aliases():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[NotificationChannel.__table__])

    try:
        async with session_factory() as db:
            db.add(
                NotificationChannel(
                    channel_type="email",
                    name="legacy-email",
                    dify_endpoint="",
                    dify_api_key="",
                    input_mapping={},
                )
            )
            await db.commit()

            result = await list_notification_channels(db)
            await db.commit()

            channels = result["data"]
            channel_types = {item.channel_type for item in channels}
            assert "email_workflow" in channel_types
            assert "wechat_workflow" not in channel_types
            assert "in_app" not in channel_types
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_channel_persists_message_field():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Agent.__table__, NotificationChannel.__table__])

    try:
        async with session_factory() as db:
            agent = Agent(
                name="notify-agent",
                description="",
                capability_tags=[],
                dify_endpoint="https://example.com/v1/workflows/run",
                dify_api_key="agent-key",
                input_params=[
                    {"name": "subject", "type": "string", "required": True},
                    {"name": "message", "type": "string", "required": True},
                ],
                output_params=[],
            )
            db.add(agent)
            await db.flush()

            result = await update_channel(
                "wechat_workflow",
                NotificationChannelUpdate(
                    name="微信渠道",
                    agent_id=agent.id,
                    input_params=[
                        {"name": "subject", "type": "string", "required": True, "value": "{{title}}"},
                        {"name": "message", "type": "string", "required": True, "value": ""},
                    ],
                    message_field="message",
                ),
                db,
            )
            await db.commit()

            saved = result["data"]
            assert saved.message_field == "message"
            assert isinstance(saved.input_mapping, dict)
            assert saved.input_mapping.get("message_field") == "message"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_channel_persists_custom_channel():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[NotificationChannel.__table__])

    try:
        async with session_factory() as db:
            create_result = await create_channel(
                NotificationChannelCreate(
                    channel_type="sms_workflow",
                ),
                db,
            )
            await db.commit()

            assert create_result["data"].channel_type == "sms_workflow"
            assert create_result["data"].name == "sms_workflow"

            list_result = await list_notification_channels(db)
            listed_types = {item.channel_type for item in list_result["data"]}
            assert "sms_workflow" in listed_types
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_channel_rejects_duplicate_channel_type():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[NotificationChannel.__table__])

    try:
        async with session_factory() as db:
            await create_channel(
                NotificationChannelCreate(
                    channel_type="sms_workflow",
                ),
                db,
            )

            with pytest.raises(HTTPException) as exc_info:
                await create_channel(
                    NotificationChannelCreate(
                        channel_type="sms_workflow",
                    ),
                    db,
                )

            assert exc_info.value.status_code == 400
            assert "已存在" in str(exc_info.value.detail)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_channel_removes_custom_channel():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[NotificationChannel.__table__])

    try:
        async with session_factory() as db:
            await create_channel(
                NotificationChannelCreate(
                    channel_type="sms_workflow",
                ),
                db,
            )
            await db.flush()

            await delete_channel("sms_workflow", db)
            await db.commit()

            result = await list_notification_channels(db)
            channel_types = {item.channel_type for item in result["data"]}
            assert "sms_workflow" not in channel_types
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_channel_allows_any_existing_channel_type():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[NotificationChannel.__table__])

    try:
        async with session_factory() as db:
            await create_channel(
                NotificationChannelCreate(
                    channel_type="email_workflow",
                ),
                db,
            )

            await delete_channel("email_workflow", db)
            await db.commit()

            result = await list_notification_channels(db)
            channel_types = {item.channel_type for item in result["data"]}
            assert "email_workflow" not in channel_types
    finally:
        await engine.dispose()


