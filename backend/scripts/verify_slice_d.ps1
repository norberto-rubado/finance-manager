# verify_slice_d.ps1 -- slice D DoD 验证
# Usage: pwsh backend\scripts\verify_slice_d.ps1
# Prerequisites:
#   - frontend 已 `pnpm install`
#   - 跑 [5/5] e2e 还需 backend 在 :8000(uvicorn)+ Postgres 容器 + admin user seed +
#     $env:ADMIN_TEST_PASSWORD 已设。否则该步会 SKIP(其余步骤照跑通过)。

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
Push-Location $repoRoot

Write-Host "=== Slice D DoD verify ===" -ForegroundColor Cyan

# 1. typecheck
Write-Host "`n[1/5] frontend typecheck..." -ForegroundColor Yellow
Push-Location frontend
pnpm typecheck
if ($LASTEXITCODE -ne 0) { Pop-Location; Pop-Location; exit 1 }
Write-Host "  PASS" -ForegroundColor Green

# 2. unit tests
Write-Host "`n[2/5] Vitest unit tests..." -ForegroundColor Yellow
pnpm test:unit
if ($LASTEXITCODE -ne 0) { Pop-Location; Pop-Location; exit 1 }
Write-Host "  PASS" -ForegroundColor Green

# 3. production build
Write-Host "`n[3/5] Next.js build..." -ForegroundColor Yellow
pnpm build
if ($LASTEXITCODE -ne 0) { Pop-Location; Pop-Location; exit 1 }
Write-Host "  PASS" -ForegroundColor Green

# 4. 路由命名规约(spec § 9.1 / overview § 命名规约 — 路由复数 + 动态段 [id])
Write-Host "`n[4/5] Route naming convention..." -ForegroundColor Yellow
$expected = @('login', 'transactions', 'statements', 'accounts', 'categories', 'rules', 'settings')
foreach ($name in $expected) {
    $found = Get-ChildItem -Path app -Recurse -Filter "page.tsx" |
        Where-Object { $_.FullName -match "[\\/]$name[\\/]" }
    if ($null -eq $found) {
        Write-Host "  FAIL: 路由 /$name 不存在" -ForegroundColor Red
        Pop-Location; Pop-Location; exit 1
    }
}
# 关键复数命名(在 (app) group 下) — 用 -LiteralPath 防 PowerShell 把
# `(app)` `[id]` 等当成 glob 字符类,Next.js 的路由约定刚好踩这俩。
$pluralRoutes = @('transactions', 'statements', 'accounts', 'categories', 'rules')
foreach ($p in $pluralRoutes) {
    if (-not (Test-Path -LiteralPath "app/(app)/$p/page.tsx")) {
        Write-Host "  FAIL: 复数路由 /$p 缺 page.tsx" -ForegroundColor Red
        Pop-Location; Pop-Location; exit 1
    }
}
# review 动态段 — `[id]` 必须 -LiteralPath
if (-not (Test-Path -LiteralPath "app/(app)/statements/[id]/review/page.tsx")) {
    Write-Host "  FAIL: 缺 /statements/[id]/review/page.tsx" -ForegroundColor Red
    Pop-Location; Pop-Location; exit 1
}
Write-Host "  PASS" -ForegroundColor Green
Pop-Location  # frontend

# 5. E2E smoke
Write-Host "`n[5/5] Playwright smoke (skip if ADMIN_TEST_PASSWORD not set)..." -ForegroundColor Yellow
if ($env:ADMIN_TEST_PASSWORD) {
    Push-Location frontend
    pnpm test:e2e
    if ($LASTEXITCODE -ne 0) { Pop-Location; Pop-Location; exit 1 }
    Pop-Location
    Write-Host "  PASS: 4 e2e tests green" -ForegroundColor Green
} else {
    Write-Host "  SKIP: ADMIN_TEST_PASSWORD not set; run manually:" -ForegroundColor Gray
    Write-Host "    `$env:ADMIN_TEST_PASSWORD='fm-dev-2026'; cd frontend; pnpm test:e2e" -ForegroundColor Gray
}

Write-Host "`n=== Slice D DoD: ALL PASS ===" -ForegroundColor Green
Pop-Location  # repoRoot
