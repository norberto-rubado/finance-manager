"""MCP server entry。

启动流程:
1) 读 settings(.env)
2) 调 backend POST /api/admin/tokens/verify 自检 token 合法
3) 注册所有 tools(import tools.* 触发 register())
4) 起 transport:stdio(本机调试)/ http(prod;ASGI 适配)
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import sys

import httpx
from mcp import types as mcp_types
from mcp.server.lowlevel import Server

from app.config import get_settings
from app.errors import MCPToolError
from app.tools import get_handler, get_tool_definitions

logger = logging.getLogger("mcp_server")

server: Server = Server("finance-manager-mcp")


@server.list_tools()
async def _list_tools() -> list[mcp_types.Tool]:
    return get_tool_definitions()


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    handler = get_handler(name)
    if handler is None:
        raise ValueError(f"unknown tool: {name}")
    try:
        return await handler(arguments or {})
    except MCPToolError as e:
        # 把错误以 TextContent 返回(MCP 协议层错误用 raise,但工具语义错误用 content text)
        return [
            mcp_types.TextContent(
                type="text",
                text=json.dumps({"error": e.to_dict()}, ensure_ascii=False),
            )
        ]


async def _verify_token_self_check() -> None:
    """启动时调 backend /verify 一次,token 不合法立刻退出(避免起来后第一次工具调用才 fail)。"""
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.mcp_backend_url, timeout=10,
    ) as c:
        resp = await c.post(
            "/api/admin/tokens/verify",
            headers={"Authorization": f"Bearer {settings.mcp_api_token}"},
        )
        if resp.status_code == 401:
            logger.error("MCP_API_TOKEN invalid (backend rejected). Exiting.")
            sys.exit(2)
        if resp.status_code >= 500:
            logger.error(
                "backend not reachable (%d): %s. Will exit; restart docker-compose.",
                resp.status_code,
                resp.text,
            )
            sys.exit(3)
        if resp.status_code != 200:
            # 其它 4xx(404 = endpoint 缺失,403 = scope 不足,等等)— 视为不可用
            logger.error(
                "backend /api/admin/tokens/verify returned %d: %s. Exiting.",
                resp.status_code,
                resp.text,
            )
            sys.exit(2)
        body = resp.json()
        logger.info(
            "token verified, user=%s scopes=%s",
            body.get("username"),
            body.get("scopes"),
        )


def _register_all_tools() -> None:
    """import tools.* 触发各模块 register() 副作用。"""
    for tool_module in [
        "app.tools.list_transactions",
        "app.tools.get_summary",
        "app.tools.get_account_balances",
        "app.tools.find_merchant",
        "app.tools.list_pending_dedup_pairs",
        "app.tools.list_pending_classifications",
        "app.tools.add_transaction",
        "app.tools.update_category",
        "app.tools.bulk_update_category_by_merchant",
        "app.tools.confirm_dedup_pair",
    ]:
        try:
            importlib.import_module(tool_module)
        except ImportError:
            # Task 6 阶段 tool 模块尚未存在,允许 silent skip
            logger.debug("tool module %s not found yet (slice E in progress?)", tool_module)


async def main_stdio() -> None:
    from mcp.server.stdio import stdio_server

    _register_all_tools()
    await _verify_token_self_check()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def main_http(host: str, port: int) -> None:
    """HTTP transport(prod 部署用)。"""
    import uvicorn
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    _register_all_tools()
    await _verify_token_self_check()

    manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        json_response=True,
    )

    async def asgi_app(scope, receive, send):
        if scope["type"] != "http":
            return
        await manager.handle_request(scope, receive, send)

    config = uvicorn.Config(
        asgi_app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )
    s = uvicorn.Server(config)
    await s.serve()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    host = args.host or settings.mcp_host
    port = args.port or settings.mcp_port

    if args.transport == "stdio":
        asyncio.run(main_stdio())
    else:
        asyncio.run(main_http(host, port))


if __name__ == "__main__":
    main()
