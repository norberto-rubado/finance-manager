# Finance Manager — MCP Server

10 个工具(6 read + 4 write)封装 finance-manager backend REST API,
按 MCP 协议暴露给 OpenClaw / Hermes Agent。

## 启动

### 本地 dev(stdio)— 与 MCP Inspector 调试

```powershell
cd mcp_server
python -m app.main --transport stdio
# 或 npx @modelcontextprotocol/inspector python -m app.main
```

### Docker / VPS prod(HTTP 9443 via Caddy)

`docker-compose --profile prod up -d` 起完整栈,Caddy 反代 `https://<domain>:9443/`。

## 配置(`.env`)

| 变量 | 默认 | 说明 |
|---|---|---|
| `MCP_BACKEND_URL` | `http://backend:8000` | backend HTTP 内网地址(本机 dev 用 `http://127.0.0.1:8000`) |
| `MCP_API_TOKEN` | — | 必填,backend 创建的 token plain;启动时 server 自检调 backend /verify |
| `MCP_HOST` | `0.0.0.0` | HTTP transport 监听地址 |
| `MCP_PORT` | `8765` | HTTP transport 端口 |

## 工具清单(spec § 8.1)

| 工具 | 类型 | 说明 |
|---|---|---|
| list_transactions | read | 按时间/分类/账户筛选交易 |
| get_summary | read | 按 day/week/month/year 汇总 |
| get_account_balances | read | 账户余额(流水推算) |
| find_merchant | read | 按关键词聚合商家 |
| list_pending_dedup_pairs | read | 待审核去重对 |
| list_pending_classifications | read | 待分类交易 |
| add_transaction | write | 手动加一笔(支持 agent 对话录入) |
| update_category | write | 改单条交易分类 |
| bulk_update_category_by_merchant | write | 批量按商家改类(可选加规则) |
| confirm_dedup_pair | write | 确认/拒绝去重对 |

## 错误码(spec § 8.3)

| MCP 错误码 | 触发场景 |
|---|---|
| AUTH_FAILED | Bearer 缺失或失效 |
| NOT_FOUND | transaction_id / pair_id / category 不存在 |
| VALIDATION_ERROR | 入参不合法 |
| CONFLICT | 重复确认 dedup_pair / 已存在的资源 |
| BACKEND_ERROR | backend 5xx 透传 |
