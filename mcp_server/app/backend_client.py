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

    async def get(self, url: str, **kwargs) -> dict:
        resp = await self._client.get(url, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx_to_mcp_error(e) from e
        return resp.json()

    async def post(self, url: str, **kwargs) -> dict:
        resp = await self._client.post(url, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx_to_mcp_error(e) from e
        # 204 No Content
        if resp.status_code == 204:
            return {}
        return resp.json()

    async def patch(self, url: str, **kwargs) -> dict:
        resp = await self._client.patch(url, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx_to_mcp_error(e) from e
        if resp.status_code == 204:
            return {}
        return resp.json()

    async def delete(self, url: str, **kwargs) -> dict:
        resp = await self._client.delete(url, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx_to_mcp_error(e) from e
        if resp.status_code == 204:
            return {}
        return resp.json()


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
