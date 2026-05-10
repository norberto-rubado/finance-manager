# mcp_smoke.ps1 -- spec § DoD #1-2,e2e 冒烟测 MCP server stdio + JSON-RPC
#
# Pre-conditions:
#   - backend uvicorn 在 :8000(必须真跑 — MCP server 启动会调 backend /verify)
#   - 数据库有 admin user + 至少一个 ApiToken
#   - $env:MCP_API_TOKEN 已设(明文 token,与 db 中 hash 对应)
#   - mcp_server/.venv 已就绪(pip install -e .[dev])
#
# Usage:
#   $env:MCP_API_TOKEN = "<plain-token>"
#   pwsh backend/tests/e2e/mcp_smoke.ps1
#
$ErrorActionPreference = "Stop"

if (-not $env:MCP_API_TOKEN) {
    Write-Host "FAIL: MCP_API_TOKEN env not set" -ForegroundColor Red
    exit 1
}

$repoRoot = (Resolve-Path "$PSScriptRoot\..\..\..\").Path
$mcpDir = Join-Path $repoRoot "mcp_server"
$venvPy = Join-Path $mcpDir ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "FAIL: mcp_server venv not found at $venvPy" -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] Build JSON-RPC requests..." -ForegroundColor Yellow

# MCP initialize handshake
$initMsg = @{
    jsonrpc = "2.0"; id = 1; method = "initialize"
    params = @{
        protocolVersion = "2024-11-05"
        capabilities = @{}
        clientInfo = @{ name = "mcp_smoke.ps1"; version = "0.1" }
    }
} | ConvertTo-Json -Compress -Depth 10

$initNotif = @{ jsonrpc = "2.0"; method = "notifications/initialized" } | ConvertTo-Json -Compress

$listMsg = @{
    jsonrpc = "2.0"; id = 2; method = "tools/list"; params = @{}
} | ConvertTo-Json -Compress -Depth 10

$callMsg = @{
    jsonrpc = "2.0"; id = 3; method = "tools/call"
    params = @{
        name = "list_transactions"
        arguments = @{ limit = 5 }
    }
} | ConvertTo-Json -Compress -Depth 10

# stdin 拼成 4 行(每行一个 JSON-RPC message,以 \n 分隔)
$stdin = "$initMsg`n$initNotif`n$listMsg`n$callMsg`n"

Write-Host "[2/3] Spawn mcp_server stdio + pipe stdin..." -ForegroundColor Yellow

# 后台跑 mcp_server,5 秒超时
$pinfo = New-Object System.Diagnostics.ProcessStartInfo
$pinfo.FileName = $venvPy
$pinfo.WorkingDirectory = $mcpDir
$pinfo.Arguments = "-m app.main --transport stdio"
$pinfo.RedirectStandardInput = $true
$pinfo.RedirectStandardOutput = $true
$pinfo.RedirectStandardError = $true
$pinfo.UseShellExecute = $false
$pinfo.EnvironmentVariables["MCP_API_TOKEN"] = $env:MCP_API_TOKEN
$pinfo.EnvironmentVariables["MCP_BACKEND_URL"] = ($env:MCP_BACKEND_URL ?? "http://127.0.0.1:8000")

$proc = [System.Diagnostics.Process]::Start($pinfo)
$proc.StandardInput.Write($stdin)
$proc.StandardInput.Close()

# 5 秒收输出
if (-not $proc.WaitForExit(5000)) {
    $proc.Kill()
    Write-Host "FAIL: mcp_server timed out (5s)" -ForegroundColor Red
    exit 1
}

$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()

Write-Host "[3/3] Parse responses + assert..." -ForegroundColor Yellow
Write-Host "stderr (token verify log):" -ForegroundColor DarkGray
Write-Host $stderr -ForegroundColor DarkGray

$lines = $stdout -split "`n" | Where-Object { $_.Trim() }
$responses = @()
foreach ($line in $lines) {
    try {
        $obj = $line | ConvertFrom-Json
        if ($obj.id -ne $null) { $responses += $obj }
    } catch {
        # 非 JSON 行 (e.g. notifications) 跳过
    }
}

# Assert id=2 (tools/list) 返回 10 个工具
$listResp = $responses | Where-Object { $_.id -eq 2 } | Select-Object -First 1
if (-not $listResp) {
    Write-Host "FAIL: no tools/list response" -ForegroundColor Red
    Write-Host "stdout:" $stdout
    exit 1
}
$tools = $listResp.result.tools
$expected = @("list_transactions", "get_summary", "get_account_balances",
              "find_merchant", "list_pending_dedup_pairs", "list_pending_classifications",
              "add_transaction", "update_category",
              "bulk_update_category_by_merchant", "confirm_dedup_pair")
$names = $tools | ForEach-Object { $_.name } | Sort-Object
$expectedSorted = $expected | Sort-Object
if (Compare-Object $names $expectedSorted) {
    Write-Host "FAIL: tool list mismatch" -ForegroundColor Red
    Write-Host "got:" ($names -join ", ")
    Write-Host "expected:" ($expectedSorted -join ", ")
    exit 1
}
Write-Host "  PASS: 10 tools listed" -ForegroundColor Green

# Assert id=3 (tools/call list_transactions) 返回 content[0].text 是合法 JSON
$callResp = $responses | Where-Object { $_.id -eq 3 } | Select-Object -First 1
if (-not $callResp) {
    Write-Host "FAIL: no tools/call response" -ForegroundColor Red
    exit 1
}
$content = $callResp.result.content[0]
if ($content.type -ne "text") {
    Write-Host "FAIL: content not text type" -ForegroundColor Red
    exit 1
}
$payload = $content.text | ConvertFrom-Json
if ($payload.PSObject.Properties.Name -notcontains "transactions") {
    if ($payload.error) {
        Write-Host "FAIL: tool returned error: $($payload.error.code) - $($payload.error.message)" -ForegroundColor Red
    } else {
        Write-Host "FAIL: response missing 'transactions' field" -ForegroundColor Red
        Write-Host $content.text
    }
    exit 1
}
Write-Host "  PASS: list_transactions returned $($payload.transactions.Count) tx" -ForegroundColor Green

Write-Host "`n=== MCP smoke: ALL PASS ===" -ForegroundColor Green
exit 0
