import asyncio
import re
from urllib.parse import urlsplit, urlunsplit

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.llm_config import LLMConfig
from app.models.llm_usage_log import LLMUsageLog


class LLMServiceError(RuntimeError):
    """Raised when the upstream LLM service is unavailable or returns invalid responses."""


class LLMClient:
    def __init__(self):
        # Use split timeout phases so connection issues fail fast while generation can still run longer.
        self._request_timeout = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=30.0)
        self._client = httpx.AsyncClient(timeout=self._request_timeout)

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

    async def _post_with_retry(self, endpoint: str, payload: dict, headers: dict, provider: str, model_name: str):
        max_attempts = 3
        retryable_network_errors = (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
            httpx.ReadError,
        )

        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                is_retryable = status == 429 or (status is not None and status >= 500)
                if is_retryable and attempt < max_attempts:
                    await asyncio.sleep(0.6 * attempt)
                    continue
                body = ""
                try:
                    body = (exc.response.text or "")[:300] if exc.response is not None else ""
                except Exception:
                    body = ""
                raise LLMServiceError(
                    f"LLM call failed ({provider}/{model_name}): HTTP {status}; {body}".strip()
                ) from exc
            except retryable_network_errors as exc:
                if attempt < max_attempts:
                    await asyncio.sleep(0.6 * attempt)
                    continue
                raise LLMServiceError(
                    f"LLM call failed ({provider}/{model_name}): {exc}. Please retry in a moment."
                ) from exc
            except Exception as exc:
                raise LLMServiceError(f"LLM call failed ({provider}/{model_name}): {exc}") from exc

    async def chat(self, config: LLMConfig, messages: list[dict]) -> dict:
        """Send chat request to LLM based on provider config"""
        endpoint = self._resolve_chat_endpoint(config.api_endpoint)
        if endpoint != (config.api_endpoint or "").strip():
            logger.info("Normalized LLM endpoint from '{}' to '{}'", config.api_endpoint, endpoint)

        if not endpoint or not config.api_key or not config.model_name:
            raise LLMServiceError("LLM config incomplete: endpoint, api_key, and model_name are required")

        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        prefs = config.user_preferences or {}
        payload = {
            "model": config.model_name,
            "messages": messages,
            "max_tokens": config.max_tokens,
        }
        if prefs.get("temperature_enabled", True):
            payload["temperature"] = config.temperature
        if prefs.get("top_p_enabled", True):
            payload["top_p"] = config.top_p
        try:
            response = await self._post_with_retry(
                endpoint=endpoint,
                payload=payload,
                headers=headers,
                provider=config.provider or "unknown",
                model_name=config.model_name or "unknown",
            )
            result = response.json()
            return {
                "content": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "usage": result.get("usage", {}),
            }
        except LLMServiceError:
            raise
        except Exception as e:
            logger.error(f"LLM call failed ({config.provider}/{config.model_name}): {e}")
            raise LLMServiceError(f"LLM call failed ({config.provider}/{config.model_name}): {e}") from e

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
