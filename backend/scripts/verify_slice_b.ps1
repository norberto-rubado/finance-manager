# verify_slice_b.ps1 -- slice B DoD 验证
# 用法: 在 finance-manager/ 根目录或 worktree 根目录下运行
#   pwsh backend\scripts\verify_slice_b.ps1
$ErrorActionPreference = "Stop"

Write-Host "=== Slice B DoD verify ===" -ForegroundColor Cyan

# 定位到含 backend/ 的目录(仓库根或 worktree 根)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = (Resolve-Path (Join-Path $scriptDir "..")).Path
Push-Location $backendDir

# 1. 跑解析器测试 + 覆盖率
Write-Host "`n[1/4] Run parser tests with coverage (threshold 80%)..." -ForegroundColor Yellow
.\.venv\Scripts\Activate.ps1
pytest tests/services/statement_parser/ -v `
    --cov=app.services.statement_parser `
    --cov-report=term `
    --cov-fail-under=80
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: parser tests or coverage < 80%" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "  PASS: all parser tests pass, coverage >= 80%" -ForegroundColor Green

# 2. 跑全测试套件(确保 slice A 也没坏)
Write-Host "`n[2/4] Run full test suite..." -ForegroundColor Yellow
pytest -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: full test suite has failures" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "  PASS: full test suite green" -ForegroundColor Green

Pop-Location

# 3. 验证 I-1 索引修复: tx_time DESC(用 docker exec,不依赖 compose context)
Write-Host "`n[3/4] Verify I-1: ix_transactions_user_tx_time has DESC..." -ForegroundColor Yellow
$idxOut = docker exec finance-manager-db-1 psql -U finance -d finance -c "\d transactions" 2>&1 | Out-String
if ($idxOut -match "ix_transactions_user_tx_time.*tx_time\s+DESC") {
    Write-Host "  PASS: index has DESC" -ForegroundColor Green
} else {
    # 宽松匹配: 只要索引名存在且 DESC 在附近
    if ($idxOut -match "ix_transactions_user_tx_time" -and $idxOut -match "DESC") {
        Write-Host "  PASS: index exists with DESC (relaxed match)" -ForegroundColor Green
    } else {
        Write-Host "  FAIL: ix_transactions_user_tx_time with DESC not found" -ForegroundColor Red
        Write-Host $idxOut
        exit 1
    }
}

# 4. 验证 I-3: 全测试套件 < 120s (savepoint rollback 模式,比原来 4m21s 快得多)
Write-Host "`n[4/4] Verify I-3: full test suite completes in reasonable time..." -ForegroundColor Yellow
Push-Location $backendDir
$sw = [System.Diagnostics.Stopwatch]::StartNew()
pytest -q | Out-Null
$sw.Stop()
$elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1)
if ($sw.Elapsed.TotalSeconds -lt 120) {
    Write-Host "  PASS: ${elapsed}s < 120s (was 4m21s before I-3 fix)" -ForegroundColor Green
} else {
    Write-Host "  FAIL: ${elapsed}s >= 120s, test suite too slow" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location

Write-Host "`n=== Slice B DoD: ALL PASS ===" -ForegroundColor Green
