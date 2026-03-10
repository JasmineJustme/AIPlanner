import re
from urllib.parse import urlsplit, urlunsplit

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.llm_config import LLMConfig
from app.models.llm_usage_log import LLMUsageLog


class LLMClient:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=120)

    def _resolve_chat_endpoint(self, api_endpoint: str | None) -> str:
        endpoint = (api_endpoint or "").strip()
        if not endpoint:
            return endpoint

        endpoint = endpoint.rstrip("/")
        if endpoint.lower().endswith("/chat/completions"):
            return endpoint

        parsed = urlsplit(endpoint)
        path = parsed.path.rstrip("/")
        should_append_chat_path = not path or re.search(r"/v\d+$", path)
        if not should_append_chat_path:
            return endpoint

        normalized_path = f"{path}/chat/completions" if path else "/chat/completions"
        return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, parsed.query, parsed.fragment))

    async def chat(self, config: LLMConfig, messages: list[dict]) -> dict:
        """Send chat request to LLM based on provider config"""
        endpoint = self._resolve_chat_endpoint(config.api_endpoint)
        if endpoint != (config.api_endpoint or "").strip():
            logger.info("Normalized LLM endpoint from '{}' to '{}'", config.api_endpoint, endpoint)

        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_tokens": config.max_tokens,
        }
        try:
            response = await self._client.post(
                endpoint, json=payload, headers=headers
            )
            response.raise_for_status()
            result = response.json()
            return {
                "content": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "usage": result.get("usage", {}),
            }
        except Exception as e:
            logger.error(f"LLM call failed ({config.provider}/{config.model_name}): {e}")
            raise

    async def log_usage(
        self,
        db: AsyncSession,
        purpose: str,
        model_name: str,
        usage: dict,
        request_id: str = None,
    ):
        log = LLMUsageLog(
            purpose=purpose,
            model_name=model_name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            estimated_cost=0.0,
            request_id=request_id,
        )
        db.add(log)

    async def close(self):
        await self._client.aclose()


llm_client = LLMClient()
