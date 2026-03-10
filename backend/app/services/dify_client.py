import httpx
from loguru import logger


class DifyClient:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=300)

    @staticmethod
    def _derive_workflow_run_url(endpoint: str) -> str:
        """Normalize user-provided Dify endpoints to the workflow run API."""
        url = (endpoint or "").strip().rstrip("/")
        if not url:
            return url
        if url.endswith("/workflows/run"):
            return url
        if "/v1/" in url:
            return url.split("/v1/", 1)[0] + "/v1/workflows/run"
        if url.endswith("/v1"):
            return url + "/workflows/run"
        if url.endswith("/workflows"):
            return url + "/run"
        if url.endswith("/run"):
            return url[: -len("/run")] + "/workflows/run"
        return url + "/workflows/run"

    async def call_agent(self, endpoint: str, api_key: str, inputs: dict, timeout: int = 300) -> dict:
        """Call a configured Dify workflow for Agent execution."""
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"inputs": inputs, "response_mode": "blocking", "user": "audit-coworker"}
        request_url = self._derive_workflow_run_url(endpoint)
        try:
            response = await self._client.post(request_url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Dify Agent call failed: {e}")
            raise

    async def call_workflow(self, endpoint: str, api_key: str, inputs: dict, timeout: int = 300) -> dict:
        """Call Dify Workflow"""
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"inputs": inputs, "response_mode": "blocking", "user": "audit-coworker"}
        request_url = self._derive_workflow_run_url(endpoint)
        try:
            response = await self._client.post(request_url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Dify Workflow call failed: {e}")
            raise

    @staticmethod
    def _derive_parameters_url(endpoint: str) -> str:
        """Derive the Dify /parameters URL from any Dify API endpoint.

        Dify endpoints follow the pattern:
          {host}/v1/chat-messages
          {host}/v1/completion-messages
          {host}/v1/workflows/run
        The parameters endpoint is always at {host}/v1/parameters.
        """
        url = endpoint.rstrip("/")
        # Find /v1/ or trailing /v1 and build from there
        v1_idx = url.find("/v1/")
        if v1_idx != -1:
            return url[: v1_idx] + "/v1/parameters"
        if url.endswith("/v1"):
            return url + "/parameters"
        # Fallback: strip last path segment (handles custom non-Dify APIs)
        return url.rsplit("/", 1)[0] + "/parameters"

    async def test_connection(self, endpoint: str, api_key: str) -> dict:
        """Test connectivity to a Dify endpoint.
        Returns {"connected": bool, "status_code": int|None, "error": str|None}
        """
        headers = {"Authorization": f"Bearer {api_key}"}
        test_url = self._derive_parameters_url(endpoint)
        try:
            response = await self._client.get(test_url, headers=headers, timeout=10)
            if response.status_code == 200:
                return {"connected": True, "status_code": 200, "error": None}
            if response.status_code == 401:
                return {"connected": False, "status_code": 401, "error": "API Key 无效或已过期"}
            if response.status_code == 403:
                return {"connected": False, "status_code": 403, "error": "API Key 权限不足"}
            if response.status_code == 404:
                return {"connected": False, "status_code": 404, "error": f"Endpoint 路径不存在: {test_url}"}
            return {
                "connected": False,
                "status_code": response.status_code,
                "error": f"服务返回异常状态码: {response.status_code}",
            }
        except httpx.ConnectError:
            return {"connected": False, "status_code": None, "error": f"无法连接到服务器，请检查地址是否正确: {endpoint}"}
        except httpx.TimeoutException:
            return {"connected": False, "status_code": None, "error": f"连接超时（10秒），服务器无响应: {endpoint}"}
        except Exception as e:
            return {"connected": False, "status_code": None, "error": f"连接异常: {str(e)}"}

    async def close(self):
        await self._client.aclose()


dify_client = DifyClient()
