# verify_slice_c.ps1 -- slice C DoD verification
# Usage: run from finance-manager/ root or worktree root
#   pwsh backend\scripts\verify_slice_c.ps1
#
# Prerequisites:
#   - docker-compose up -d db
#   - alembic upgrade head
#   - python -m app.db.seed
#   - set $env:ADMIN_TEST_PASSWORD for e2e step (optional)
$ErrorActionPreference = "Stop"

Write-Host "=== Slice C DoD verify ===" -ForegroundColor Cyan

# Locate backend dir relative to this script
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = (Resolve-Path (Join-Path $scriptDir "..")).Path
Push-Location $backendDir

# 1. Run full test suite (slice A + B + C)
Write-Host "`n[1/5] Run full test suite..." -ForegroundColor Yellow
.\.venv\Scripts\Activate.ps1
pytest -q --maxfail=3
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: test suite has failures" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-Host "  PASS: full test suite green" -ForegroundColor Green

# 2. Verify B-poly-1: no codepoint matching helpers in ccb_credit_pdf
Write-Host "`n[2/5] Verify B-poly-1: no codepoint matching..." -ForegroundColor Yellow
$ccbSrc = Get-Content "app\services\statement_parser\ccb_credit_pdf.py" -Raw
if ($ccbSrc -match "_has_codepoints" -or $ccbSrc -match "_starts_with_codepoints" -or $ccbSrc -match "_YINLIAN_CP") {
    Write-Host "  FAIL: ccb_credit_pdf still has codepoint helpers" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-Host "  PASS: codepoint helpers removed" -ForegroundColor Green

# 3. Verify B-poly-2: _is_repayment uses substring order matching
Write-Host "`n[3/5] Verify B-poly-2: _is_repayment uses substring..." -ForegroundColor Yellow
$pyCheck = @"
from app.services.statement_parser.ccb_credit_pdf import _is_repayment
import sys
sys.exit(0 if (_is_repayment(u'银联入账77432') and not _is_repayment(u'联银账入')) else 1)
"@
python -c $pyCheck
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: _is_repayment still order-agnostic" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-Host "  PASS: substring order respected" -ForegroundColor Green

# 4. Verify I-5: seed.py no longer hardcodes placeholder
Write-Host "`n[4/5] Verify I-5: seed.py no placeholder hardcoded..." -ForegroundColor Yellow
$seedSrc = Get-Content "app\db\seed.py" -Raw
if ($seedSrc -match 'password_hash\s*=\s*"\$2b\$12\$placeholder') {
    Write-Host "  FAIL: seed.py still hardcodes placeholder" -ForegroundColor Red
    Pop-Location; exit 1
}
if ($seedSrc -notmatch "admin_password_hash") {
    Write-Host "  FAIL: seed.py does not read Settings.admin_password_hash" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-Host "  PASS: seed reads from Settings" -ForegroundColor Green

# 5. E2E import_flow.ps1 (optional -- requires uvicorn + ADMIN_TEST_PASSWORD)
Pop-Location

Write-Host "`n[5/5] E2E import_flow.ps1..." -ForegroundColor Yellow
if ($env:ADMIN_TEST_PASSWORD) {
    $e2eScript = Join-Path $backendDir "tests\e2e\import_flow.ps1"
    pwsh $e2eScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAIL: e2e script failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "  PASS: e2e all 7 steps green" -ForegroundColor Green
} else {
    Write-Host "  SKIP: ADMIN_TEST_PASSWORD not set; run manually:" -ForegroundColor Gray
    Write-Host "    `$env:ADMIN_TEST_PASSWORD='fm-dev-2026'" -ForegroundColor Gray
    Write-Host "    pwsh backend\tests\e2e\import_flow.ps1" -ForegroundColor Gray
}

Write-Host "`n=== Slice C DoD: ALL PASS ===" -ForegroundColor Green
