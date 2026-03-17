from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.message import Message
from app.models.notification_channel import NotificationChannel
from app.models.notification_pref import NotificationPref, NotificationGlobalPref
from app.services.sse_manager import sse_manager
from app.services.dify_client import dify_client
from loguru import logger
from datetime import UTC, datetime


class NotificationService:
    async def notify(
        self,
        db: AsyncSession,
        msg_type: str,
        title: str,
        content: str,
        related_type: str = None,
        related_id: str = None,
        action_url: str = None,
    ):
        """Create a notification and broadcast via SSE + external channels"""
        # 1. Create message record
        msg = Message(
            type=msg_type,
            title=title,
            content=content,
            related_type=related_type,
            related_id=related_id,
            action_url=action_url,
        )
        db.add(msg)
        await db.flush()

        # 2. Broadcast via SSE
        event_type = msg_type  # Use message type as SSE event
        await sse_manager.broadcast(event_type, {
            "id": msg.id,
            "type": msg_type,
            "title": title,
            "content": content,
            "action_url": action_url,
        })

        # 3. Check user preferences and send external notifications
        prefs_q = select(NotificationPref).where(
            NotificationPref.message_type == msg_type,
            NotificationPref.user_id == "default"
        )
        pref = (await db.execute(prefs_q)).scalar_one_or_none()

        # Check DND
        global_q = select(NotificationGlobalPref).where(NotificationGlobalPref.user_id == "default")
        global_pref = (await db.execute(global_q)).scalar_one_or_none()

        if global_pref and global_pref.dnd_start and global_pref.dnd_end:
            now_time = datetime.now(UTC).strftime("%H:%M")
            if global_pref.dnd_start <= now_time <= global_pref.dnd_end:
                logger.info(f"DND active, skipping external push for {msg_type}")
                return msg

        if pref:
            if pref.email_enabled:
                await self._push_external(db, "email_workflow", title, content)
                msg.external_pushed = True
            if pref.wechat_enabled:
                await self._push_external(db, "wechat_workflow", title, content)
                msg.external_pushed = True

        await db.flush()
        return msg

    def _render_param_value(self, value: object, title: str, content: str) -> str:
        text = str(value or "")
        return (
            text.replace("{{title}}", title)
            .replace("{{content}}", content)
            .replace("{title}", title)
            .replace("{content}", content)
        )

    def _build_inputs(self, channel: NotificationChannel, title: str, content: str) -> dict:
        mapping = channel.input_mapping if isinstance(channel.input_mapping, dict) else {}
        message_field = str(mapping.get("message_field") or "").strip()

        # New format: input_mapping.input_params = [{name, value, ...}]
        raw_params = mapping.get("input_params") if isinstance(mapping.get("input_params"), list) else []
        if raw_params:
            inputs: dict[str, object] = {}
            for item in raw_params:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                if item.get("value") not in (None, ""):
                    value = item.get("value")
                elif item.get("default") not in (None, ""):
                    value = item.get("default")
                elif item.get("required"):
                    value = ""
                else:
                    continue
                if isinstance(value, str):
                    inputs[name] = self._render_param_value(value, title, content)
                else:
                    inputs[name] = value
            if message_field:
                # Selected message field always carries the reminder body.
                inputs[message_field] = content
            if inputs:
                return inputs

        # Legacy fallback: semantic_key -> target_field
        inputs = {}
        for key, field in mapping.items():
            if not isinstance(field, str):
                continue
            if "subject" in key.lower() or "title" in key.lower():
                inputs[field] = title
            elif "content" in key.lower() or "body" in key.lower() or "message" in key.lower():
                inputs[field] = content
            else:
                inputs[field] = content
        if message_field:
            inputs[message_field] = content
        return inputs

    async def _push_external(self, db: AsyncSession, channel_type: str, title: str, content: str):
        """Push notification via Dify Workflow"""
        channel_q = select(NotificationChannel).where(
            NotificationChannel.channel_type == channel_type,
            NotificationChannel.is_enabled == True
        )
        channel = (await db.execute(channel_q)).scalar_one_or_none()
        if not channel:
            return

        try:
            inputs = self._build_inputs(channel, title, content)
            await dify_client.call_workflow(channel.dify_endpoint, channel.dify_api_key, inputs)
            logger.info(f"External notification sent via {channel_type}")
        except Exception as e:
            logger.error(f"External notification failed ({channel_type}): {e}")


notification_service = NotificationService()
