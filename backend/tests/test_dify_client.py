import pytest

from app.services.dify_client import DifyClient


@pytest.mark.parametrize(
    ("raw_endpoint", "expected"),
    [
        ("https://api.example.com/v1", "https://api.example.com/v1/workflows/run"),
        ("https://api.example.com/v1/", "https://api.example.com/v1/workflows/run"),
        ("https://api.example.com/v1/workflows/run", "https://api.example.com/v1/workflows/run"),
        ("https://api.example.com/v1/run", "https://api.example.com/v1/workflows/run"),
        ("https://api.example.com/custom/run", "https://api.example.com/custom/workflows/run"),
    ],
)
def test_derive_workflow_run_url(raw_endpoint, expected):
    assert DifyClient._derive_workflow_run_url(raw_endpoint) == expected


@pytest.mark.parametrize(
    ("raw_endpoint", "expected"),
    [
        ("https://api.example.com/v1", "https://api.example.com/v1/parameters"),
        ("https://api.example.com/v1/workflows/run", "https://api.example.com/v1/parameters"),
        ("https://api.example.com/v1/run", "https://api.example.com/v1/parameters"),
    ],
)
def test_derive_parameters_url(raw_endpoint, expected):
    assert DifyClient._derive_parameters_url(raw_endpoint) == expected


@pytest.mark.asyncio
async def test_call_agent_posts_to_normalized_workflow_run_url(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"status": "succeeded"}, "ok": True}

    async def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    client = DifyClient()
    monkeypatch.setattr(client._client, "post", fake_post)

    result = await client.call_agent("https://api.example.com/v1", "secret", {"a": 1}, timeout=42)

    assert result == {"data": {"status": "succeeded"}, "ok": True}
    assert captured["url"] == "https://api.example.com/v1/workflows/run"
    assert captured["json"] == {"inputs": {"a": 1}, "response_mode": "blocking", "user": "audit-coworker"}
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["timeout"] == 42

    await client.close()


@pytest.mark.parametrize(
    "response_json, expected_error",
    [
        ({"data": {"status": "failed", "error": "workflow failed"}}, "status=failed"),
        ({"data": {"status": "running"}}, "status=running"),
        ({"data": {}}, "status=unknown"),
    ],
)
@pytest.mark.asyncio
async def test_call_agent_requires_succeeded_status(monkeypatch, response_json, expected_error):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return response_json

    async def fake_post(url, json, headers, timeout):
        return FakeResponse()

    client = DifyClient()
    monkeypatch.setattr(client._client, "post", fake_post)

    with pytest.raises(ValueError, match=expected_error):
        await client.call_agent("https://api.example.com/v1", "secret", {"a": 1}, timeout=42)

    await client.close()


