# verify_slice_e.ps1 -- slice E DoD 验证(本机可自动化部分)
#
# Usage:
#   pwsh backend\scripts\verify_slice_e.ps1
#
# Pre-conditions:
#   - 在 finance-manager/ 根或 worktree 根
#   - backend/.venv 装好 + alembic 已 upgrade head
#   - mcp_server/.venv 装好
#   - Postgres 容器跑着
#   - $env:ADMIN_TEST_PASSWORD 已设(给 step 3 e2e 用,未设则该步 SKIP)
#
# Notes:
#   - spec DoD #4(VPS 上 9443/agent 端到端)和 #5(实跑 cron + age + rclone)
#     依赖真 VPS,本脚本只做本机可自动化的 sanity:compose config + Caddyfile
#     validate + backup.sh 语法 + .env.example 完整性。

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
Push-Location $repoRoot

Write-Host "=== Slice E DoD verify ===" -ForegroundColor Cyan

# 1. backend pytest 全绿(含 Task 0-5 新增 admin/tokens + /verify + /manual + /me)
Write-Host "`n[1/7] backend pytest..." -ForegroundColor Yellow
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/ -q --maxfail=3 2>&1 | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) {
    Pop-Location; Pop-Location
    Write-Host "  FAIL backend tests" -ForegroundColor Red
    exit 1
}
Write-Host "  PASS" -ForegroundColor Green
Pop-Location

# 2. mcp_server pytest 全绿(Task 6-17:10 工具 unit + integration + token verify)
Write-Host "`n[2/7] mcp_server pytest..." -ForegroundColor Yellow
Push-Location mcp_server
.\.venv\Scripts\python.exe -m pytest tests/ -q 2>&1 | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) {
    Pop-Location; Pop-Location
    Write-Host "  FAIL mcp tests" -ForegroundColor Red
    exit 1
}
Write-Host "  PASS" -ForegroundColor Green
Pop-Location

# 3. mcp_server stdio 启动 — token 合法时能列 10 工具
#    需要 backend uvicorn 在跑 + ADMIN_TEST_PASSWORD + admin user seed
Write-Host "`n[3/7] mcp_smoke.ps1 stdio JSON-RPC..." -ForegroundColor Yellow
if (-not $env:ADMIN_TEST_PASSWORD) {
    Write-Host "  SKIP: ADMIN_TEST_PASSWORD not set; manually:" -ForegroundColor Gray
    Write-Host "    `$env:ADMIN_TEST_PASSWORD='fm-dev-2026'" -ForegroundColor Gray
    Write-Host "    pwsh backend\scripts\verify_slice_e.ps1" -ForegroundColor Gray
} else {
    # 启 backend(后台)
    Push-Location backend
    $bk = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
        -ArgumentList "-m","uvicorn","app.main:app","--port","8000" `
        -PassThru -WindowStyle Hidden
    Pop-Location
    Start-Sleep -Seconds 4

    try {
        # login + create token
        $body = @{ username="admin"; password=$env:ADMIN_TEST_PASSWORD } | ConvertTo-Json
        $sess = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/auth/login -Method Post `
            -Body $body -ContentType "application/json" -SessionVariable s
        $tok = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/admin/tokens -Method Post `
            -Body (@{ name="verify-e" } | ConvertTo-Json) -ContentType "application/json" -WebSession $s
        $env:MCP_API_TOKEN = $tok.plain_token
        $env:MCP_BACKEND_URL = "http://127.0.0.1:8000"

        pwsh backend\tests\e2e\mcp_smoke.ps1
        if ($LASTEXITCODE -ne 0) { throw "mcp_smoke failed" }
        Write-Host "  PASS" -ForegroundColor Green
    } finally {
        if ($bk -and -not $bk.HasExited) {
            Stop-Process -Id $bk.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

# 4. docker-compose --profile prod config 校验(yaml syntax + 5 prod services 齐全)
Write-Host "`n[4/7] docker-compose --profile prod config sanity..." -ForegroundColor Yellow
$cfg = docker-compose --profile prod config 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: compose config invalid" -ForegroundColor Red
    Write-Host $cfg
    Pop-Location; exit 1
}
$expected_services = @("db_prod","backend_prod","mcp_prod","frontend_prod","caddy")
foreach ($svc in $expected_services) {
    if ($cfg -notmatch "(?m)^\s+${svc}:") {
        Write-Host "  FAIL: prod service $svc missing in compose config" -ForegroundColor Red
        Pop-Location; exit 1
    }
}
Write-Host "  PASS: 5 prod services present (db_prod/backend_prod/mcp_prod/frontend_prod/caddy)" -ForegroundColor Green

# 5. Caddyfile 语法校验(用与 prod 一致的 slothcroissant/caddy-cloudflaredns 镜像 —
#    上游 caddy:2 不含 caddy-dns/cloudflare 模块,会误报 'module not registered')
#    用 `caddy adapt --validate`(只检查 Caddyfile 语法 + JSON 可生成),不做 ACME
#    provisioning(那需要真 token + 真域名,留给 VPS deploy)。
#    若环境无 docker 或拉不到镜像,设 $env:SKIP_CADDY_VALIDATE=1 跳过。
Write-Host "`n[5/7] Caddyfile validate..." -ForegroundColor Yellow
if ($env:SKIP_CADDY_VALIDATE) {
    Write-Host "  SKIP: SKIP_CADDY_VALIDATE set" -ForegroundColor Gray
} else {
    # 占位 token 用 40 字符 alphanumeric 模拟 Cloudflare API token 格式,避开 issuer
    # 模块的 sanity 检查(虽然 adapt 不真 provision,但 Caddyfile parser 早期已检查)
    docker run --rm `
        -e CADDY_ACME_EMAIL=verify@example.com `
        -e CLOUDFLARE_API_TOKEN=fakefakefakefakefakefakefakefakefakefake `
        -e DOMAIN=verify.example.com `
        -v ${PWD}/Caddyfile:/etc/caddy/Caddyfile:ro `
        slothcroissant/caddy-cloudflaredns:latest `
        caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile --validate 2>&1 | Select-Object -Last 3
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAIL: Caddyfile invalid (or slothcroissant/caddy-cloudflaredns image not pullable; set `$env:SKIP_CADDY_VALIDATE=1 to skip)" -ForegroundColor Red
        Pop-Location; exit 1
    }
    Write-Host "  PASS" -ForegroundColor Green
}

# 6. backup.sh 语法静态检查(bash -n)
Write-Host "`n[6/7] backup.sh syntax check..." -ForegroundColor Yellow
bash -n scripts/backup.sh
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: backup.sh syntax" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-Host "  PASS" -ForegroundColor Green

# 7. .env.example 完整性 — 必含 MCP / DOMAIN / CADDY / ADMIN 字段
Write-Host "`n[7/7] .env.example completeness..." -ForegroundColor Yellow
$env_keys = @("DOMAIN","CLOUDFLARE_API_TOKEN","CADDY_ACME_EMAIL",
              "MCP_BACKEND_URL","MCP_API_TOKEN","ADMIN_USERNAME","ADMIN_PASSWORD_HASH")
$envFile = Get-Content .env.example -Raw
foreach ($k in $env_keys) {
    if ($envFile -notmatch "(?m)^\s*${k}=") {
        Write-Host "  FAIL: .env.example missing key $k" -ForegroundColor Red
        Pop-Location; exit 1
    }
}
Write-Host "  PASS" -ForegroundColor Green

Write-Host "`n=== Slice E DoD: ALL PASS (steps 3-4 of spec DoD partially deferred to actual VPS) ===" -ForegroundColor Green
Pop-Location
exit 0
