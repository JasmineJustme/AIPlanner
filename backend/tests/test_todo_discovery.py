import json
from datetime import datetime, timedelta

from sqlalchemy import select

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.engine.todo_discovery import TodoDiscoveryEngine
from app.models.base import Base
from app.models.datasource import DataSource
from app.models.llm_config import LLMConfig
from app.models.responsibility import Responsibility
from app.models.todo import Todo


@pytest.mark.asyncio
async def test_extract_discovered_todos_supports_required_fields():
    engine = TodoDiscoveryEngine()
    payload = {
        "todos": [
            {
                "待办摘要": "完成审计复核",
                "任务描述": "整理本周凭证并提交复核意见",
                "priority": "high",
                "紧急性原因": "月底结账",
                "是否需要开始循环": True,
                "需要用户确认时间": "2026-03-20T10:00:00",
                "执行方": "用户",
                "工作职责": ["发票审计", "归档管理"],
                "tags": ["财务"],
                "project": "月结",
            }
        ]
    }

    discovered = engine._extract_discovered_todos(payload)

    assert len(discovered) == 1
    item = discovered[0]
    assert item["title"] == "完成审计复核"
    assert item["description"] == "整理本周凭证并提交复核意见"
    assert item["priority"] == "high"
    assert item["review_reason"] == "月底结账"
    assert item["is_recurring"] is True
    assert item["due_date"] is not None
    assert item["execution_mode"] == "user"
    assert item["responsibility_titles"] == ["发票审计", "归档管理"]
    assert "urgency_reason:月底结账" in item["tags"]


@pytest.mark.asyncio
async def test_extract_discovered_todos_accepts_single_responsibility_alias():
    engine = TodoDiscoveryEngine()
    payload = {
        "todos": [
            {
                "todo_summary": "复核审计计划",
                "task_description": "根据职责要求更新下周审计计划",
                "priority": "medium",
                "responsibility": "内控审计",
            }
        ]
    }

    discovered = engine._extract_discovered_todos(payload)

    assert len(discovered) == 1
    assert discovered[0]["responsibility_titles"] == ["内控审计"]


@pytest.mark.asyncio
async def test_smart_discover_syncs_before_llm_and_creates_todos(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                DataSource.__table__,
                LLMConfig.__table__,
                Responsibility.__table__,
                Todo.__table__,
            ],
        )

    call_order: list[str] = []
    captured_prompt = {"text": ""}

    async def fake_sync_all_datasources(_db):
        call_order.append("sync")
        return {"mail": {"messages": [{"subject": "提醒"}]}}

    async def fake_chat(_cfg, messages):
        call_order.append("chat")
        captured_prompt["text"] = str(messages[1]["content"])
        return {
            "content": json.dumps(
                {
                    "todos": [
                        {
                            "todo_summary": "跟进发票归档",
                            "task_description": "需要用户先确认归档范围",
                            "priority": "medium",
                            "urgency_reason": "防止遗漏",
                            "start_recurring": False,
                            "confirm_by": "2026-03-21T09:00:00",
                            "executor": "system",
                            "responsibilities": ["发票审计"],
                            "tags": ["归档"],
                            "project": "票据治理",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            "usage": {},
        }

    async def fake_log_usage(_db, _purpose, _model_name, _usage):
        return None

    async def fake_run_todo_dedup(_self, _db, _candidates, _dedup_at):
        return {"removed_candidate_ids": set(), "touched_keep_candidate_ids": set(), "duplicates": []}

    monkeypatch.setattr("app.engine.todo_discovery.sync_all_datasources", fake_sync_all_datasources)
    monkeypatch.setattr("app.engine.todo_discovery.llm_client.chat", fake_chat)
    monkeypatch.setattr("app.engine.todo_discovery.llm_client.log_usage", fake_log_usage)
    monkeypatch.setattr(TodoDiscoveryEngine, "_run_todo_dedup", fake_run_todo_dedup)

    try:
        async with session_factory() as db:
            db.add(
                DataSource(
                    type="mail",
                    name="邮件",
                    dify_endpoint="https://example.com/v1/workflows/run",
                    dify_api_key="secret",
                    is_enabled=True,
                )
            )
            db.add(
                LLMConfig(
                    purpose="todo_analysis",
                    provider="openai",
                    model_name="glm-4-flash",
                    api_endpoint="https://example.com/v1",
                    api_key="secret",
                    prompt_template="{current_time}\n{datasource_info}\n{responsibilities}\n{todo_desc}",
                )
            )
            db.add(
                Responsibility(
                    title="发票审计",
                    description="检查发票合规性",
                )
            )
            await db.commit()

            result = await TodoDiscoveryEngine().smart_discover(db)
            await db.commit()

            todos = (await db.execute(__import__("sqlalchemy").select(Todo))).scalars().all()

        assert call_order[:2] == ["sync", "chat"]
        assert result["created_count"] == 1
        assert len(todos) == 1
        assert todos[0].title == "跟进发票归档"
        assert todos[0].review_reason == "防止遗漏"
        assert todos[0].execution_mode == "system"
        assert todos[0].due_date is not None
        assert todos[0].responsibility_titles == ["发票审计"]
        assert len(todos[0].responsibility_ids) == 1
        assert "+08:00" in captured_prompt["text"]
        assert "{todo_desc}" not in captured_prompt["text"]
        assert "现有待办" not in captured_prompt["text"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_smart_discover_dedups_existing_and_new_system_todos_and_resets_created_at(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                DataSource.__table__,
                LLMConfig.__table__,
                Responsibility.__table__,
                Todo.__table__,
            ],
        )

    dedup_time = datetime(2026, 3, 19, 10, 0, 0)

    async def fake_sync_all_datasources(_db):
        return {"mail": {"messages": []}}

    async def fake_chat(_cfg, _messages):
        return {
            "content": json.dumps(
                {
                    "todos": [
                        {
                            "todo_summary": "整理审计材料并提交",
                            "task_description": "把资料整理成统一包",
                            "priority": "medium",
                            "executor": "system",
                        },
                        {
                            "todo_summary": "新增唯一任务",
                            "task_description": "不重复",
                            "priority": "low",
                            "executor": "system",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            "usage": {},
        }

    async def fake_log_usage(_db, _purpose, _model_name, _usage):
        return None

    async def fake_run_todo_dedup(_self, _db, candidates, _dedup_at):
        keep_existing = next(item["candidate_id"] for item in candidates if item["kind"] == "existing")
        remove_new = next(item["candidate_id"] for item in candidates if item["kind"] == "new" and item["title"] == "整理审计材料并提交")
        return {
            "removed_candidate_ids": {remove_new},
            "touched_keep_candidate_ids": {keep_existing},
            "duplicates": [
                {
                    "keep_id": keep_existing,
                    "remove_id": remove_new,
                    "relation": "overlap",
                    "reason": "目标任务已覆盖新增内容",
                }
            ],
        }

    monkeypatch.setattr("app.engine.todo_discovery.sync_all_datasources", fake_sync_all_datasources)
    monkeypatch.setattr("app.engine.todo_discovery.llm_client.chat", fake_chat)
    monkeypatch.setattr("app.engine.todo_discovery.llm_client.log_usage", fake_log_usage)
    monkeypatch.setattr(TodoDiscoveryEngine, "_run_todo_dedup", fake_run_todo_dedup)
    monkeypatch.setattr("app.engine.todo_discovery.utc_now_naive", lambda: dedup_time)

    try:
        async with session_factory() as db:
            db.add(DataSource(type="mail", name="邮件", is_enabled=True))
            db.add(
                LLMConfig(
                    purpose="todo_analysis",
                    provider="openai",
                    model_name="glm-4-flash",
                    api_endpoint="https://example.com/v1",
                    api_key="secret",
                    prompt_template="{current_time}\n{datasource_info}\n{responsibilities}",
                )
            )
            old_created_at = dedup_time - timedelta(days=2)
            db.add(
                Todo(
                    id="existing-system-todo",
                    title="整理审计材料",
                    source="system",
                    status="pending_confirm",
                    execution_mode="system",
                    created_at=old_created_at,
                )
            )
            await db.commit()

            result = await TodoDiscoveryEngine().smart_discover(db)
            await db.commit()

            todos = (await db.execute(select(Todo).where(Todo.source == "system"))).scalars().all()

        assert result["dedup_count"] == 1
        assert result["created_count"] == 1
        assert len(todos) == 2

        existing = next(todo for todo in todos if todo.id == "existing-system-todo")
        assert existing.created_at == dedup_time
        assert all(todo.title != "整理审计材料并提交" for todo in todos)
        assert any(todo.title == "新增唯一任务" for todo in todos)
    finally:
        await engine.dispose()


def test_sanitize_prompt_template_removes_fixed_json_output_marker_block():
    engine = TodoDiscoveryEngine()
    raw_template = (
        "前文\n"
        "# ==== FIXED_JSON_OUTPUT_FORMAT_START (DO NOT EDIT) ====\n"
        "{\"todos\": []}\n"
        "# ==== FIXED_JSON_OUTPUT_FORMAT_END ====\n"
        "后文 {current_time}"
    )

    cleaned = engine._sanitize_prompt_template(raw_template)

    assert "FIXED_JSON_OUTPUT_FORMAT_START" not in cleaned
    assert "FIXED_JSON_OUTPUT_FORMAT_END" not in cleaned
    assert "后文 {current_time}" in cleaned


