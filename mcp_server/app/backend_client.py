"""httpx-based backend client — 注入 Bearer header + 错误映射 + 单例。"""
from __future__ import annotations

import httpx

from app.config import get_settings
from app.errors import httpx_to_mcp_error


class BackendClient:
    """所有工具共用一个 httpx.AsyncClient,handler 直接调 self.get/post/...。"""

    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=httpx.Timeout(15.0, connect=5.0),
            transport=transport,        # 测试时塞 MockTransport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        """单一 HTTP 入口:统一 raise_for_status → MCPToolError 映射 + 204 → {}。"""
        resp = await self._client.request(method, url, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx_to_mcp_error(e) from e
        # 204 No Content — 没有 body,返 {} 让 caller 不必做 None 判定
        if resp.status_code == 204:
            return {}
        return resp.json()

    async def get(self, url: str, **kwargs) -> dict:
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> dict:
        return await self._request("POST", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> dict:
        return await self._request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> dict:
        return await self._request("DELETE", url, **kwargs)


_client: BackendClient | None = None


def get_backend_client() -> BackendClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = BackendClient(s.mcp_backend_url, s.mcp_api_token)
    return _client


def set_backend_client_for_tests(client: BackendClient) -> None:
    """tests 用 — 注入带 MockTransport 的 client。"""
    global _client
    _client = client


def reset_backend_client_for_tests() -> None:
    global _client
    _client = None
