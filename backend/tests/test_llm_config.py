import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import httpx

from app.api.config_llm import get_llm_config, update_llm_config
from app.models.base import Base
from app.models.llm_config import LLMConfig
from app.schemas.llm_config import LLMConfigUpdate
from app.services.llm_client import llm_client


@pytest.mark.asyncio
async def test_update_llm_config_persists_sampling_switches():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[LLMConfig.__table__])

    try:
        async with session_factory() as db:
            await update_llm_config(
                "orchestration",
                LLMConfigUpdate(
                    provider="openai",
                    model_name="gpt-4o-mini",
                    api_endpoint="https://example.com/v1",
                    api_key="secret",
                    temperature=0.8,
                    temperature_enabled=False,
                    top_p=0.95,
                    top_p_enabled=False,
                    max_tokens=2048,
                    prompt_template="{current_time}\n{todo_desc}\n{agent_desc}\n{wagent_desc}\n{workflow_desc}",
                ),
                db,
            )
            await db.commit()

            result = await get_llm_config("orchestration", db)
            stored = result["data"]
            db_cfg = (await db.get(LLMConfig, stored.id))

        assert stored.temperature == 0.8
        assert stored.temperature_enabled is False
        assert stored.top_p == 0.95
        assert stored.top_p_enabled is False
        assert db_cfg is not None
        assert db_cfg.user_preferences["temperature_enabled"] is False
        assert db_cfg.user_preferences["top_p_enabled"] is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_llm_config_rejects_orchestration_prompt_without_required_placeholders():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[LLMConfig.__table__])

    try:
        async with session_factory() as db:
            with pytest.raises(HTTPException) as exc:
                await update_llm_config(
                    "orchestration",
                    LLMConfigUpdate(prompt_template="Only {current_time} provided"),
                    db,
                )
            assert exc.value.status_code == 400
            detail = exc.value.detail
            assert isinstance(detail, dict)
            assert detail.get("field") == "prompt_template"
            assert detail.get("error_code") == "MISSING_REQUIRED_PLACEHOLDERS"
            missing = detail.get("missing_placeholders") or []
            assert "{todo_desc}" in missing
            assert "{agent_desc}" in missing
            assert "{wagent_desc}" in missing
            assert "{workflow_desc}" in missing
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_llm_config_rejects_todo_analysis_prompt_without_required_placeholders():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[LLMConfig.__table__])

    try:
        async with session_factory() as db:
            with pytest.raises(HTTPException) as exc:
                await update_llm_config(
                    "todo_analysis",
                    LLMConfigUpdate(prompt_template="Only {current_time} provided"),
                    db,
                )
            assert exc.value.status_code == 400
            detail = exc.value.detail
            assert isinstance(detail, dict)
            assert detail.get("purpose") == "todo_analysis"
            missing = detail.get("missing_placeholders") or []
            assert "{datasource_info}" in missing
            assert "{responsibilities}" in missing
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_llm_config_rejects_todo_dedup_prompt_without_required_placeholders():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[LLMConfig.__table__])

    try:
        async with session_factory() as db:
            with pytest.raises(HTTPException) as exc:
                await update_llm_config(
                    "todo_dedup",
                    LLMConfigUpdate(prompt_template="Only {current_time} provided"),
                    db,
                )
            assert exc.value.status_code == 400
            detail = exc.value.detail
            assert isinstance(detail, dict)
            assert detail.get("purpose") == "todo_dedup"
            assert "{todo_desc}" in (detail.get("missing_placeholders") or [])
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_llm_config_rejects_unknown_placeholders():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[LLMConfig.__table__])

    try:
        async with session_factory() as db:
            with pytest.raises(HTTPException) as exc:
                await update_llm_config(
                    "todo_analysis",
                    LLMConfigUpdate(
                        prompt_template=(
                            "{current_time}\n{datasource_info}\n{responsibilities}\n{invalid_token}"
                        )
                    ),
                    db,
                )
            assert exc.value.status_code == 400
            detail = exc.value.detail
            assert isinstance(detail, dict)
            assert detail.get("error_code") == "UNKNOWN_PLACEHOLDERS"
            assert "{invalid_token}" in (detail.get("unknown_placeholders") or [])
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_llm_config_allows_todo_analysis_optional_todo_desc_placeholder():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[LLMConfig.__table__])

    try:
        async with session_factory() as db:
            result = await update_llm_config(
                "todo_analysis",
                LLMConfigUpdate(
                    prompt_template=(
                        "{current_time}\n{datasource_info}\n{responsibilities}\n{todo_desc}"
                    )
                ),
                db,
            )
            await db.commit()
            assert result["code"] == 200
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_llm_config_accepts_orchestration_prompt_with_required_placeholders():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[LLMConfig.__table__])

    valid_prompt = "\n".join([
        "{current_time}",
        "{todo_desc}",
        "{agent_desc}",
        "{wagent_desc}",
        "{workflow_desc}",
    ])

    try:
        async with session_factory() as db:
            result = await update_llm_config(
                "orchestration",
                LLMConfigUpdate(prompt_template=valid_prompt),
                db,
            )
            await db.commit()
            assert result["code"] == 200
    finally:
        await engine.dispose()


class _FakeResponse:
    def __init__(self, body: dict | None = None):
        self._body = body or {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


@pytest.mark.asyncio
async def test_llm_client_chat_omits_disabled_sampling_params(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_post(url, json, headers, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse()

    monkeypatch.setattr(llm_client._client, "post", fake_post)

    cfg = LLMConfig(
        purpose="orchestration",
        provider="openai",
        model_name="gpt-4o-mini",
        api_endpoint="https://example.com/v1",
        api_key="secret",
        temperature=0.7,
        top_p=0.9,
        max_tokens=1024,
        prompt_template="",
        user_preferences={"temperature_enabled": False, "top_p_enabled": False},
    )

    result = await llm_client.chat(cfg, [{"role": "user", "content": "hello"}])

    payload = captured["json"]
    assert result["content"] == "ok"
    assert isinstance(payload, dict)
    assert payload["model"] == "gpt-4o-mini"
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert payload["max_tokens"] == 1024
    assert "temperature" not in payload
    assert "top_p" not in payload


@pytest.mark.asyncio
async def test_llm_client_chat_retries_transient_disconnect(monkeypatch):
    attempts = {"count": 0}

    async def fake_post(url, json, headers, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return _FakeResponse()

    monkeypatch.setattr(llm_client._client, "post", fake_post)

    cfg = LLMConfig(
        purpose="todo_analysis",
        provider="openai",
        model_name="glm-4-flash",
        api_endpoint="https://example.com/v1",
        api_key="secret",
        max_tokens=1024,
        prompt_template="",
    )

    result = await llm_client.chat(cfg, [{"role": "user", "content": "hello"}])

    assert result["content"] == "ok"
    assert attempts["count"] == 2


def _make_cfg():
    return LLMConfig(
        purpose="orchestration",
        provider="openai",
        model_name="test-model",
        api_endpoint="https://example.com/v1",
        api_key="secret",
        max_tokens=1024,
        prompt_template="",
    )


@pytest.mark.asyncio
async def test_llm_client_chat_extracts_reasoning_content_field(monkeypatch):
    """Models like DeepSeek-R1 return reasoning in a dedicated message field."""

    body = {
        "choices": [
            {
                "message": {
                    "content": '{"result": "hello"}',
                    "reasoning_content": "Let me think step by step...",
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }

    async def fake_post(url, json, headers, **kwargs):
        return _FakeResponse(body)

    monkeypatch.setattr(llm_client._client, "post", fake_post)

    result = await llm_client.chat(_make_cfg(), [{"role": "user", "content": "hi"}])

    assert result["content"] == '{"result": "hello"}'
    assert result["reasoning_content"] == "Let me think step by step..."
    assert result["usage"]["total_tokens"] == 30


@pytest.mark.asyncio
async def test_llm_client_chat_strips_inline_think_tags(monkeypatch):
    """Models that embed <think> tags inside content."""

    body = {
        "choices": [
            {
                "message": {
                    "content": (
                        "<think>\nI need to analyze this carefully.\n"
                        "Step 1: parse the input\n</think>\n"
                        '{"todos": []}'
                    ),
                }
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 15, "total_tokens": 20},
    }

    async def fake_post(url, json, headers, **kwargs):
        return _FakeResponse(body)

    monkeypatch.setattr(llm_client._client, "post", fake_post)

    result = await llm_client.chat(_make_cfg(), [{"role": "user", "content": "hi"}])

    assert result["content"] == '{"todos": []}'
    assert "analyze this carefully" in result["reasoning_content"]
    assert "<think>" not in result["content"]


@pytest.mark.asyncio
async def test_llm_client_chat_prefers_dedicated_field_over_inline_tags(monkeypatch):
    """When both reasoning_content field and inline <think> tags exist,
    the dedicated field takes precedence."""

    body = {
        "choices": [
            {
                "message": {
                    "content": "<think>inline thought</think>actual answer",
                    "reasoning_content": "dedicated reasoning",
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    async def fake_post(url, json, headers, **kwargs):
        return _FakeResponse(body)

    monkeypatch.setattr(llm_client._client, "post", fake_post)

    result = await llm_client.chat(_make_cfg(), [{"role": "user", "content": "hi"}])

    assert result["content"] == "actual answer"
    assert result["reasoning_content"] == "dedicated reasoning"


@pytest.mark.asyncio
async def test_llm_client_chat_standard_model_no_reasoning(monkeypatch):
    """Standard models without any thinking fields still work fine."""

    body = {
        "choices": [{"message": {"content": "Hello! How can I help?"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10},
    }

    async def fake_post(url, json, headers, **kwargs):
        return _FakeResponse(body)

    monkeypatch.setattr(llm_client._client, "post", fake_post)

    result = await llm_client.chat(_make_cfg(), [{"role": "user", "content": "hi"}])

    assert result["content"] == "Hello! How can I help?"
    assert result["reasoning_content"] == ""
    assert result["usage"]["total_tokens"] == 10


@pytest.mark.asyncio
async def test_llm_client_chat_multiple_think_blocks(monkeypatch):
    """Content with multiple <think> blocks should merge them all."""

    body = {
        "choices": [
            {
                "message": {
                    "content": (
                        "<think>First thought</think>"
                        "Part one. "
                        "<think>Second thought</think>"
                        "Part two."
                    ),
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    async def fake_post(url, json, headers, **kwargs):
        return _FakeResponse(body)

    monkeypatch.setattr(llm_client._client, "post", fake_post)

    result = await llm_client.chat(_make_cfg(), [{"role": "user", "content": "hi"}])

    assert "<think>" not in result["content"]
    assert "Part one." in result["content"]
    assert "Part two." in result["content"]
    assert "First thought" in result["reasoning_content"]
    assert "Second thought" in result["reasoning_content"]
