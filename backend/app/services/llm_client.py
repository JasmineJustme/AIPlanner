import asyncio
import re
from urllib.parse import urlsplit, urlunsplit

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.llm_config import LLMConfig
from app.models.llm_usage_log import LLMUsageLog

_THINK_TAG_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


class LLMServiceError(RuntimeError):
    """Raised when the upstream LLM service is unavailable or returns invalid responses."""


class LLMClient:
    DEFAULT_READ_TIMEOUT = 180.0

    def __init__(self):
        self._request_timeout = httpx.Timeout(connect=15.0, read=self.DEFAULT_READ_TIMEOUT, write=30.0, pool=30.0)
        self._client = httpx.AsyncClient(timeout=self._request_timeout, verify=settings.SSL_VERIFY)

    def _build_timeout(self, read_timeout: float | None = None) -> httpx.Timeout:
        read_sec = read_timeout if read_timeout and read_timeout > 0 else self.DEFAULT_READ_TIMEOUT
        return httpx.Timeout(connect=15.0, read=read_sec, write=30.0, pool=30.0)

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

    @staticmethod
    def _extract_thinking(content: str) -> tuple[str, str]:
        """Separate inline <think>...</think> blocks from the actual content.

        Returns (clean_content, thinking_text).
        """
        thinking_parts: list[str] = []
        clean = content

        for m in _THINK_TAG_RE.finditer(content):
            thinking_parts.append(m.group(1).strip())

        if thinking_parts:
            clean = _THINK_TAG_RE.sub("", content).strip()

        return clean, "\n\n".join(thinking_parts)

    @staticmethod
    def _extract_message_fields(result: dict) -> dict:
        """Extract content, reasoning, and usage from an OpenAI-compatible response.

        Handles three scenarios:
        1. Standard response — content only in message.content
        2. Dedicated reasoning field — message.reasoning_content (DeepSeek-R1 style)
        3. Inline <think> tags — <think>...</think> embedded in message.content
        """
        message = result.get("choices", [{}])[0].get("message", {})
        raw_content = message.get("content") or ""
        usage = result.get("usage", {})

        reasoning_content = (
            message.get("reasoning_content")
            or message.get("reasoning")
            or ""
        )

        clean_content, inline_thinking = LLMClient._extract_thinking(raw_content)

        if not reasoning_content and inline_thinking:
            reasoning_content = inline_thinking

        return {
            "content": clean_content,
            "reasoning_content": reasoning_content,
            "usage": usage,
        }

    async def _post_with_retry(self, endpoint: str, payload: dict, headers: dict, provider: str, model_name: str, timeout: httpx.Timeout | None = None):
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
                response = await self._client.post(endpoint, json=payload, headers=headers, timeout=timeout)
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
        """Send chat request to LLM based on provider config.

        Returns dict with keys:
          - content: the actual answer (thinking/reasoning stripped)
          - reasoning_content: model's chain-of-thought if present (empty string otherwise)
          - usage: token usage dict
        """
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
        config_timeout = getattr(config, "timeout", None)
        request_timeout = self._build_timeout(float(config_timeout)) if config_timeout else None
        try:
            response = await self._post_with_retry(
                endpoint=endpoint,
                payload=payload,
                headers=headers,
                provider=config.provider or "unknown",
                model_name=config.model_name or "unknown",
                timeout=request_timeout,
            )
            result = response.json()
            extracted = self._extract_message_fields(result)

            if extracted["reasoning_content"]:
                logger.debug(
                    "LLM reasoning detected ({}/{}): {}…",
                    config.provider,
                    config.model_name,
                    extracted["reasoning_content"][:200],
                )

            return extracted
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
