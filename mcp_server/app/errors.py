"""MCP 错误码定义 + httpx 错误 → MCP code 映射(spec § 8.3)。"""
from __future__ import annotations

import httpx


class MCPToolError(Exception):
    """工具执行抛此异常,main.py dispatcher 捕获后包装成 MCP 错误返回。"""

    def __init__(self, code: str, message: str, *, data: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict:
        out: dict = {"code": self.code, "message": self.message}
        if self.data is not None:
            out["data"] = self.data
        return out


# spec § 8.3 错误码常量
AUTH_FAILED = "AUTH_FAILED"
NOT_FOUND = "NOT_FOUND"
VALIDATION_ERROR = "VALIDATION_ERROR"
CONFLICT = "CONFLICT"
BACKEND_ERROR = "BACKEND_ERROR"


def httpx_to_mcp_error(exc: httpx.HTTPStatusError) -> MCPToolError:
    """httpx 4xx/5xx → MCP 错误。"""
    resp = exc.response
    status = resp.status_code
    try:
        body = resp.json()
        backend_detail = body.get("detail", str(body))
    except Exception:
        backend_detail = resp.text or "unknown backend error"

    if status == 401:
        return MCPToolError(AUTH_FAILED, f"backend 401: {backend_detail}")
    if status == 404:
        return MCPToolError(NOT_FOUND, str(backend_detail))
    if status == 409:
        return MCPToolError(CONFLICT, str(backend_detail))
    if status in (400, 422):
        return MCPToolError(VALIDATION_ERROR, str(backend_detail))
    return MCPToolError(
        BACKEND_ERROR,
        f"backend {status}: {backend_detail}",
        data={"status": status},
    )
