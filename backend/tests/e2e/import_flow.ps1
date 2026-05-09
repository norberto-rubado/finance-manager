# import_flow.ps1 -- slice C DoD E2E verification
# Usage (after uvicorn is running on port 8000):
#   $env:ADMIN_TEST_PASSWORD = 'fm-dev-2026'
#   $env:E2E_RESET = '1'    # optional: truncate before run
#   pwsh backend\tests\e2e\import_flow.ps1
$ErrorActionPreference = "Stop"

# Expect caller to set ADMIN_TEST_PASSWORD before running (avoid reading hash)
$pwd = $env:ADMIN_TEST_PASSWORD
if (-not $pwd) {
    Write-Host "ERROR: please set `$env:ADMIN_TEST_PASSWORD='fm-dev-2026' (or your dev pwd)" -ForegroundColor Red
    exit 1
}

if ($env:E2E_RESET -eq "1") {
    Write-Host "[reset] truncating tx/dedup/imports..." -ForegroundColor DarkYellow
    $truncSql = "TRUNCATE statement_imports, transactions, dedup_candidates RESTART IDENTITY CASCADE;"
    docker exec finance-manager-db-1 psql -U finance -d finance -c $truncSql 2>&1 | Out-Null
}

$base = "http://127.0.0.1:8000/api"
$session = $null

Write-Host "=== Slice C E2E import_flow ===" -ForegroundColor Cyan

# [1] login
Write-Host "`n[1/7] Login..." -ForegroundColor Yellow
$loginResp = Invoke-RestMethod -Method Post -Uri "$base/auth/login" `
    -ContentType "application/json" `
    -Body (@{ username = "admin"; password = $pwd } | ConvertTo-Json) `
    -SessionVariable session
Write-Host "  PASS: logged in as $($loginResp.username)" -ForegroundColor Green

# [2] upload alipay
Write-Host "`n[2/7] Upload alipay CSV..." -ForegroundColor Yellow
$fixturesDir = (Resolve-Path (Join-Path $PSScriptRoot "..\fixtures\statements")).Path
$alipayPath = Join-Path $fixturesDir "alipay_sample.csv"
$alipayResp = Invoke-RestMethod -Method Post -Uri "$base/statements/import" `
    -WebSession $session `
    -Form @{ file = Get-Item $alipayPath }
Write-Host "  PASS: imported $($alipayResp.imported_count) tx, dedup_pending=$($alipayResp.dedup_pending_count)" -ForegroundColor Green

# [3] upload bocom PDF (may trigger dedup bridge)
Write-Host "`n[3/7] Upload bocom debit PDF..." -ForegroundColor Yellow
$bocomPath = Join-Path $fixturesDir "bocom_debit_sample.pdf"
$bocomResp = Invoke-RestMethod -Method Post -Uri "$base/statements/import" `
    -WebSession $session `
    -Form @{ file = Get-Item $bocomPath }
Write-Host "  PASS: imported $($bocomResp.imported_count) tx, dedup_pending=$($bocomResp.dedup_pending_count)" -ForegroundColor Green

# [4] /review — inspect pending
Write-Host "`n[4/7] Review bundle..." -ForegroundColor Yellow
$reviewResp = Invoke-RestMethod -Method Get -Uri "$base/statements/$($bocomResp.import_id)/review" -WebSession $session
Write-Host "  PASS: pending_pairs=$($reviewResp.pending_pairs.Count), unclassified=$($reviewResp.unclassified_transactions.Count)" -ForegroundColor Green

# [5] confirm first pending pair (if any)
Write-Host "`n[5/7] Confirm first pending pair (if any)..." -ForegroundColor Yellow
$pending = Invoke-RestMethod -Method Get -Uri "$base/dedup/pending" -WebSession $session
if ($pending.items.Count -gt 0) {
    $firstId = $pending.items[0].id
    $confirmResp = Invoke-RestMethod -Method Post -Uri "$base/dedup/$firstId/confirm" `
        -WebSession $session -ContentType "application/json" `
        -Body (@{ action = "confirm" } | ConvertTo-Json)
    if ($confirmResp.status -ne "confirmed") {
        Write-Host "  FAIL: confirm did not return confirmed status" -ForegroundColor Red
        exit 1
    }
    Write-Host "  PASS: confirmed pair_id=$firstId" -ForegroundColor Green
} else {
    Write-Host "  SKIP: no pending pairs in this run" -ForegroundColor Gray
}

# [6] /transactions — check mirror flag
Write-Host "`n[6/7] List transactions..." -ForegroundColor Yellow
$txResp = Invoke-RestMethod -Method Get -Uri "$base/transactions?limit=10" -WebSession $session
$mirrorCount = ($txResp.items | Where-Object { $_.is_mirror -eq $true }).Count
Write-Host "  PASS: total=$($txResp.total), in first 10: mirror=$mirrorCount" -ForegroundColor Green

# [7] /summary
Write-Host "`n[7/7] Summary by category..." -ForegroundColor Yellow
$sumResp = Invoke-RestMethod -Method Get -Uri "$base/summary?date_from=2025-12-01T00:00:00&date_to=2026-04-01T00:00:00" -WebSession $session
Write-Host "  PASS: total_expense=$($sumResp.total_expense), total_income=$($sumResp.total_income), breakdown_groups=$($sumResp.breakdown.Count)" -ForegroundColor Green

Write-Host "`n=== E2E import_flow: ALL PASS ===" -ForegroundColor Green
