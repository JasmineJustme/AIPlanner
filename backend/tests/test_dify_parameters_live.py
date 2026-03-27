import sqlite3
from pathlib import Path

import httpx
import pytest

from app.services.dify_client import DifyClient


def _load_target_agent() -> dict[str, str]:
    db_path = Path(__file__).resolve().parents[1] / "audit_coworker.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT name, dify_endpoint, dify_api_key FROM agents WHERE name = ?",
            ("发送信息给指定联系人",),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        pytest.skip("未找到 Agent: 发送信息给指定联系人")

    if not row["dify_endpoint"] or not row["dify_api_key"]:
        pytest.skip("目标 Agent 缺少 Dify endpoint 或 api_key")

    return {
        "name": row["name"],
        "endpoint": row["dify_endpoint"],
        "api_key": row["dify_api_key"],
    }


@pytest.mark.asyncio
async def test_parameters_endpoint_returns_input_parameter_metadata_for_target_agent():
    agent = _load_target_agent()
    parameters_url = DifyClient._derive_parameters_url(agent["endpoint"])
    headers = {"Authorization": f"Bearer {agent['api_key']}"}

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(parameters_url, headers=headers)

    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, dict)
    assert "user_input_form" in data
    assert isinstance(data["user_input_form"], list)
    assert len(data["user_input_form"]) > 0

    first_input_item = data["user_input_form"][0]
    assert isinstance(first_input_item, dict)
    assert len(first_input_item) > 0

    first_field = next(iter(first_input_item.values()))
    assert isinstance(first_field, dict)
    assert first_field.get("variable")
    assert first_field.get("label")
    assert first_field.get("type")

