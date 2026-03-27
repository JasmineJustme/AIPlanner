import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.api.settings import get_notification_prefs, update_notification_prefs
from app.models.base import Base
from app.models.notification_pref import NotificationPref
from app.schemas.settings import NotificationPrefUpdate


@pytest.mark.asyncio
async def test_update_notification_prefs_persists_channel_enabled_map():
	engine = create_async_engine("sqlite+aiosqlite:///:memory:")
	session_factory = async_sessionmaker(engine, expire_on_commit=False)

	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all, tables=[NotificationPref.__table__])

	try:
		async with session_factory() as db:
			await update_notification_prefs(
				NotificationPrefUpdate(
					message_type="task_failed",
					in_app_enabled=True,
					email_enabled=False,
					wechat_enabled=False,
					channel_enabled_map={
						"in_app": True,
						"sms_workflow": True,
					},
				),
				db,
			)
			await db.commit()

			result = await get_notification_prefs(db)
			row = next(item for item in result["data"] if item["message_type"] == "task_failed")
			assert row["channel_enabled_map"]["sms_workflow"] is True
			assert row["channel_enabled_map"]["in_app"] is True
			assert row["email_enabled"] is False
	finally:
		await engine.dispose()


@pytest.mark.asyncio
async def test_update_notification_prefs_builds_channel_map_from_legacy_fields():
	engine = create_async_engine("sqlite+aiosqlite:///:memory:")
	session_factory = async_sessionmaker(engine, expire_on_commit=False)

	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all, tables=[NotificationPref.__table__])

	try:
		async with session_factory() as db:
			await update_notification_prefs(
				NotificationPrefUpdate(
					message_type="deadline_reminder",
					in_app_enabled=True,
					email_enabled=True,
					wechat_enabled=False,
				),
				db,
			)
			await db.commit()

			result = await get_notification_prefs(db)
			row = next(item for item in result["data"] if item["message_type"] == "deadline_reminder")
			assert row["channel_enabled_map"]["in_app"] is True
			assert row["channel_enabled_map"]["email_workflow"] is True
			assert row["channel_enabled_map"]["wechat_workflow"] is False
	finally:
		await engine.dispose()


@pytest.mark.asyncio
async def test_settings_api_auto_heals_legacy_schema_without_channel_map_column():
	engine = create_async_engine("sqlite+aiosqlite:///:memory:")
	session_factory = async_sessionmaker(engine, expire_on_commit=False)

	async with engine.begin() as conn:
		await conn.execute(
			text(
				"""
				CREATE TABLE notification_prefs (
					message_type VARCHAR(30) NOT NULL,
					in_app_enabled BOOLEAN NOT NULL,
					email_enabled BOOLEAN NOT NULL,
					wechat_enabled BOOLEAN NOT NULL,
					id VARCHAR(36) NOT NULL PRIMARY KEY,
					created_at DATETIME NOT NULL,
					updated_at DATETIME NOT NULL,
					user_id VARCHAR(36) NOT NULL
				)
				"""
			)
		)

	try:
		async with session_factory() as db:
			await update_notification_prefs(
				NotificationPrefUpdate(
					message_type="system",
					in_app_enabled=True,
					email_enabled=True,
					wechat_enabled=False,
				),
				db,
			)
			await db.commit()

			result = await get_notification_prefs(db)
			row = next(item for item in result["data"] if item["message_type"] == "system")
			assert row["channel_enabled_map"]["in_app"] is True
			assert row["channel_enabled_map"]["email_workflow"] is True
			assert row["channel_enabled_map"]["wechat_workflow"] is False
	finally:
		await engine.dispose()


@pytest.mark.asyncio
async def test_update_notification_prefs_keeps_in_app_enabled():
	engine = create_async_engine("sqlite+aiosqlite:///:memory:")
	session_factory = async_sessionmaker(engine, expire_on_commit=False)

	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all, tables=[NotificationPref.__table__])

	try:
		async with session_factory() as db:
			await update_notification_prefs(
				NotificationPrefUpdate(
					message_type="system",
					in_app_enabled=False,
					email_enabled=False,
					wechat_enabled=False,
					channel_enabled_map={"in_app": False},
				),
				db,
			)
			await db.commit()

			result = await get_notification_prefs(db)
			row = next(item for item in result["data"] if item["message_type"] == "system")
			assert row["in_app_enabled"] is True
			assert row["channel_enabled_map"]["in_app"] is True
	finally:
		await engine.dispose()


