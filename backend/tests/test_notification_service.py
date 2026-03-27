from app.models.notification_channel import NotificationChannel
from app.models.notification_pref import NotificationPref
from app.services.notification_service import NotificationService


def test_build_inputs_uses_agent_style_param_values_and_template_substitution():
    service = NotificationService()
    channel = NotificationChannel(
        channel_type="email_workflow",
        name="email",
        dify_endpoint="https://example.com/v1/workflows/run",
        dify_api_key="k",
        input_mapping={
            "agent_id": "a1",
            "input_params": [
                {"name": "subject", "value": "[提醒] {{title}}", "required": True},
                {"name": "body", "value": "{{content}}", "required": True},
            ],
        },
    )

    inputs = service._build_inputs(channel, "逾期任务", "请尽快处理")

    assert inputs == {"subject": "[提醒] 逾期任务", "body": "请尽快处理"}


def test_build_inputs_falls_back_to_legacy_mapping():
    service = NotificationService()
    channel = NotificationChannel(
        channel_type="wechat_workflow",
        name="wechat",
        dify_endpoint="https://example.com/v1/workflows/run",
        dify_api_key="k",
        input_mapping={
            "title_key": "subject",
            "content_key": "message",
        },
    )

    inputs = service._build_inputs(channel, "任务提醒", "内容A")

    assert inputs["subject"] == "任务提醒"
    assert inputs["message"] == "内容A"


def test_build_inputs_forces_content_into_selected_message_field():
    service = NotificationService()
    channel = NotificationChannel(
        channel_type="email_workflow",
        name="email",
        dify_endpoint="https://example.com/v1/workflows/run",
        dify_api_key="k",
        input_mapping={
            "agent_id": "a1",
            "message_field": "message",
            "input_params": [
                {"name": "subject", "value": "{{title}}", "required": True},
                {"name": "message", "value": "manual-content", "required": True},
            ],
        },
    )

    inputs = service._build_inputs(channel, "提醒标题", "系统消息内容")

    assert inputs["subject"] == "提醒标题"
    assert inputs["message"] == "系统消息内容"


def test_resolve_enabled_channels_uses_dynamic_channel_map():
    service = NotificationService()
    pref = NotificationPref(
        message_type="system",
        in_app_enabled=True,
        email_enabled=False,
        wechat_enabled=False,
        channel_enabled_map={
            "in_app": True,
            "sms_workflow": True,
            "email_workflow": True,
        },
    )

    channels = service._resolve_enabled_channels(pref)

    assert "in_app" not in channels
    assert "sms_workflow" in channels
    assert "email_workflow" in channels


