from datetime import UTC, datetime
import importlib

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

orchestrator_module = importlib.import_module("app.engine.orchestrator")
from app.engine.orchestrator import Orchestrator
from app.models.agent import Agent
from app.models.base import Base
from app.models.llm_config import LLMConfig
from app.models.todo import Todo
from app.models.workflow import Workflow
from app.models.wagent import WAgent


def test_create_mock_plan_fills_input_params_and_time_fields():
    orchestrator = Orchestrator()
    todo = Todo(
        id="todo-1",
        title="生成周报",
        description="需要整理本周项目进展",
        source="manual",
        due_date=datetime(2026, 3, 10, 18, 0, 0),
    )
    agent = Agent(
        id="agent-1",
        name="报告Agent",
        dify_endpoint="https://example.com",
        dify_api_key="secret",
        input_params={"task_title": "", "task_description": "", "deadline": ""},
        output_params={},
    )

    result = orchestrator._create_mock_plan([todo], [agent], [], [])
    plan = result["plan"]

    assert result["status"] == "pending_confirm"
    assert plan["input_params"]["task_title"] == "生成周报"
    assert plan["input_params"]["task_description"] == "需要整理本周项目进展"
    assert plan["input_params"]["deadline"] == "2026-03-10T18:00:00"
    assert isinstance(plan["start_time"], str)
    assert plan["deadline"] == "2026-03-10T18:00:00"


def test_normalize_plan_clamps_deadline_to_earliest_todo_due_date():
    orchestrator = Orchestrator()
    todo = Todo(
        id="todo-2",
        title="完成审计",
        source="manual",
        due_date=datetime(2026, 3, 11, 12, 0, 0),
    )
    agent = Agent(
        id="agent-2",
        name="审计Agent",
        dify_endpoint="https://example.com",
        dify_api_key="secret",
        input_params={"audit_title": "", "deadline": ""},
        output_params={},
    )

    normalized = orchestrator._normalize_plan(
        {
            "plan_type": "agent",
            "recommended_id": "agent-2",
            "input_params": {"audit_title": "自定义任务"},
            "estimated_duration_minutes": 45,
            "start_time": "2026-03-11T08:00:00",
            "deadline": "2026-03-12T10:00:00",
        },
        [todo],
        [agent],
        [],
        [],
    )

    assert normalized["recommended_name"] == "审计Agent"
    assert normalized["input_params"]["audit_title"] == "自定义任务"
    assert normalized["deadline"] == "2026-03-11T12:00:00"


def test_normalize_plan_supports_list_shaped_agent_input_params():
    orchestrator = Orchestrator()
    todo = Todo(
        id="todo-3",
        title="发送提醒",
        description="提醒联系人提交周报",
        source="manual",
        due_date=datetime(2026, 3, 12, 9, 0, 0),
    )
    agent = Agent(
        id="agent-3",
        name="提醒Agent",
        dify_endpoint="https://example.com",
        dify_api_key="secret",
        input_params=[
            {"name": "task_title", "default": ""},
            {"name": "task_description", "default": ""},
            {"name": "deadline", "default": ""},
        ],
        output_params={},
    )

    normalized = orchestrator._normalize_plan(
        {
            "plan_type": "agent",
            "recommended_id": "agent-3",
            "input_params": {},
        },
        [todo],
        [agent],
        [],
        [],
    )

    assert normalized["input_params"]["task_title"] == "发送提醒"
    assert normalized["input_params"]["task_description"] == "提醒联系人提交周报"
    assert normalized["input_params"]["deadline"] == "2026-03-12T09:00:00"


def test_normalize_plan_supports_list_shaped_llm_input_params():
    orchestrator = Orchestrator()
    todo = Todo(
        id="todo-4",
        title="整理报告",
        source="manual",
        due_date=datetime(2026, 3, 13, 18, 0, 0),
    )
    agent = Agent(
        id="agent-4",
        name="报告Agent",
        dify_endpoint="https://example.com",
        dify_api_key="secret",
        input_params={"report_type": "weekly", "deadline": ""},
        output_params={},
    )

    normalized = orchestrator._normalize_plan(
        {
            "plan_type": "agent",
            "recommended_id": "agent-4",
            "input_params": [
                {"name": "report_type", "value": "monthly"},
                {"name": "deadline", "value": "2026-03-13T12:00:00"},
            ],
        },
        [todo],
        [agent],
        [],
        [],
    )

    assert normalized["input_params"]["report_type"] == "monthly"
    assert normalized["input_params"]["deadline"] == "2026-03-13T12:00:00"


def test_create_mock_plan_can_fallback_to_new_wagent_from_workflows():
    orchestrator = Orchestrator()
    todo = Todo(
        id="todo-5",
        title="跨系统整理数据",
        source="manual",
        due_date=datetime(2026, 3, 14, 17, 0, 0),
    )
    workflow = Workflow(
        id="workflow-1",
        name="数据清洗Workflow",
        dify_endpoint="https://example.com",
        dify_api_key="secret",
        input_params=[{"name": "task_title", "default": ""}],
        output_params={},
    )

    result = orchestrator._create_mock_plan([todo], [], [], [workflow])
    plan = result["plan"]

    assert result["status"] == "pending_confirm"
    assert plan["plan_type"] == "new_wagent"
    assert plan["recommended_name"] == "新建W-Agent工作流"
    assert plan["steps"][0]["workflow_id"] == "workflow-1"
    assert plan["steps"][0]["workflow_name"] == "数据清洗Workflow"


def test_normalize_plan_defaults_start_time_from_current_time_when_missing():
    orchestrator = Orchestrator()
    before = datetime.now(UTC).replace(tzinfo=None, microsecond=0)

    normalized = orchestrator._normalize_plan(
        {
            "plan_type": "agent",
            "estimated_duration_minutes": 45,
            "start_time": None,
            "deadline": None,
        },
        [
            Todo(
                id="todo-6",
                title="跟进客户",
                source="manual",
                due_date=None,
            )
        ],
        [],
        [],
        [],
    )
    after = datetime.now(UTC).replace(tzinfo=None, microsecond=0)

    start_time = datetime.fromisoformat(normalized["start_time"])
    deadline = datetime.fromisoformat(normalized["deadline"])

    assert before <= start_time <= after
    assert deadline >= start_time


def test_normalize_plan_keeps_all_declared_params_editable_for_agent():
    orchestrator = Orchestrator()
    todo = Todo(
        id="todo-7",
        title="处理报销",
        description="补全报销信息",
        source="manual",
        due_date=datetime(2026, 3, 15, 18, 0, 0),
    )
    agent = Agent(
        id="agent-7",
        name="报销Agent",
        dify_endpoint="https://example.com",
        dify_api_key="secret",
        input_params=[
            {"name": "applicant", "default": "default-user", "user_fill_enabled": True},
            {"name": "internal_token", "default": "", "user_fill_enabled": False},
        ],
        output_params={},
    )

    normalized = orchestrator._normalize_plan(
        {
            "plan_type": "agent",
            "recommended_id": "agent-7",
            "input_params": {"internal_token": "abc"},
        },
        [todo],
        [agent],
        [],
        [],
    )

    assert normalized["editable_input_keys"] == ["applicant", "internal_token"]
    assert normalized["input_params"]["applicant"] == "default-user"
    assert normalized["input_params"]["internal_token"] == "abc"


def test_filter_prompt_input_params_hides_llm_filled_params_when_flag_exists():
    orchestrator = Orchestrator()
    raw = [
        {"name": "user_param", "user_fill_enabled": True},
        {"name": "llm_param", "user_fill_enabled": False},
    ]

    filtered = orchestrator._filter_prompt_input_params(raw)

    assert isinstance(filtered, list)
    assert len(filtered) == 1
    assert filtered[0]["name"] == "llm_param"


def test_filter_prompt_input_params_keeps_all_params_when_flag_absent():
    orchestrator = Orchestrator()
    raw = [
        {"name": "legacy_param_1"},
        {"name": "legacy_param_2"},
    ]

    filtered = orchestrator._filter_prompt_input_params(raw)

    assert isinstance(filtered, list)
    assert len(filtered) == 2


@pytest.mark.asyncio
async def test_orchestrate_uses_user_prompt_template_with_required_placeholders(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, Agent.__table__, WAgent.__table__, Workflow.__table__, LLMConfig.__table__],
        )

    captured_prompt = {"value": ""}

    async def fake_chat(_cfg, messages):
        captured_prompt["value"] = messages[1]["content"]
        return {
            "content": '{"plan_type":"agent","recommended_id":"agent-prompt","recommended_name":"模板Agent","reason":"ok","input_params":{},"priority":"medium","estimated_duration_minutes":30,"start_time":null,"deadline":null,"steps":[]}',
            "usage": {},
        }

    async def fake_log_usage(*_args, **_kwargs):
        return None

    monkeypatch.setattr(orchestrator_module.llm_client, "chat", fake_chat)
    monkeypatch.setattr(orchestrator_module.llm_client, "log_usage", fake_log_usage)

    try:
        async with session_factory() as db:
            db.add(
                Todo(
                    id="todo-prompt-1",
                    title="模板测试任务",
                    source="manual",
                    status="pending_confirm",
                )
            )
            db.add(
                Agent(
                    id="agent-prompt",
                    name="模板Agent",
                    dify_endpoint="https://example.com",
                    dify_api_key="secret",
                    is_enabled=True,
                    input_params={},
                    output_params={},
                )
            )
            db.add(
                LLMConfig(
                    purpose="orchestration",
                    provider="mock",
                    model_name="mock-model",
                    api_endpoint="https://example.com",
                    api_key="secret",
                    prompt_template=(
                        "当前:{current_time}\\n"
                        "待办:{todo_desc}\\n"
                        "Agent:{agent_desc}\\n"
                        "WAgent:{wagent_desc}\\n"
                        "Workflow:{workflow_desc}\\n"
                        '示例JSON:{"k":"v"}'
                    ),
                )
            )
            await db.commit()

            orchestrator = Orchestrator()
            result = await orchestrator.orchestrate(db, ["todo-prompt-1"])

        assert result["status"] == "pending_confirm"
        assert "{todo_desc}" not in captured_prompt["value"]
        assert "模板测试任务" in captured_prompt["value"]
        assert "示例JSON:{\"k\":\"v\"}" in captured_prompt["value"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_orchestrate_legacy_placeholder_template_falls_back_to_default_prompt(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, Agent.__table__, WAgent.__table__, Workflow.__table__, LLMConfig.__table__],
        )

    captured_prompt = {"value": ""}

    async def fake_chat(_cfg, messages):
        captured_prompt["value"] = messages[1]["content"]
        return {
            "content": '{"plan_type":"agent","recommended_id":"agent-legacy","recommended_name":"默认Agent","reason":"ok","input_params":{},"priority":"medium","estimated_duration_minutes":30,"start_time":null,"deadline":null,"steps":[]}',
            "usage": {},
        }

    async def fake_log_usage(*_args, **_kwargs):
        return None

    monkeypatch.setattr(orchestrator_module.llm_client, "chat", fake_chat)
    monkeypatch.setattr(orchestrator_module.llm_client, "log_usage", fake_log_usage)

    try:
        async with session_factory() as db:
            db.add(
                Todo(
                    id="todo-legacy-1",
                    title="旧占位符测试任务",
                    source="manual",
                    status="pending_confirm",
                )
            )
            db.add(
                Agent(
                    id="agent-legacy",
                    name="默认Agent",
                    dify_endpoint="https://example.com",
                    dify_api_key="secret",
                    is_enabled=True,
                    input_params={},
                    output_params={},
                )
            )
            db.add(
                LLMConfig(
                    purpose="orchestration",
                    provider="mock",
                    model_name="mock-model",
                    api_endpoint="https://example.com",
                    api_key="secret",
                    prompt_template=(
                        "LEGACY::{current_time}\\n"
                        "{todos}\\n"
                        "{agents}\\n"
                        "{wagents}\\n"
                        "{workflows}"
                    ),
                )
            )
            await db.commit()

            orchestrator = Orchestrator()
            result = await orchestrator.orchestrate(db, ["todo-legacy-1"])

        assert result["status"] == "pending_confirm"
        assert "LEGACY::" not in captured_prompt["value"]
        assert "分析以下待办任务" in captured_prompt["value"]
        assert "旧占位符测试任务" in captured_prompt["value"]
    finally:
        await engine.dispose()


def test_sanitize_prompt_template_removes_fixed_json_output_marker_block():
    orchestrator = Orchestrator()
    raw_template = (
        "上文\n"
        "# ==== FIXED_JSON_OUTPUT_FORMAT_START (DO NOT EDIT) ====\n"
        "{\"fixed\": true}\n"
        "# ==== FIXED_JSON_OUTPUT_FORMAT_END ====\n"
        "下文 {current_time}"
    )

    cleaned = orchestrator._sanitize_prompt_template(raw_template)

    assert "FIXED_JSON_OUTPUT_FORMAT_START" not in cleaned
    assert "FIXED_JSON_OUTPUT_FORMAT_END" not in cleaned
    assert "下文 {current_time}" in cleaned

