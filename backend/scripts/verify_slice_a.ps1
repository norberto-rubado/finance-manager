# 切片 A DoD 验收脚本(Windows PowerShell 7+)
# 用法: 在 finance-manager/ 目录下跑 .\backend\scripts\verify_slice_a.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Slice A DoD Verification ===" -ForegroundColor Cyan

Write-Host "`n[1/5] docker-compose up db..." -ForegroundColor Yellow
docker-compose up -d db
Start-Sleep -Seconds 3

Write-Host "`n[2/5] alembic upgrade head..." -ForegroundColor Yellow
Set-Location backend
& .\.venv\Scripts\Activate.ps1
alembic upgrade head

Write-Host "`n[3/5] python -m app.db.seed..." -ForegroundColor Yellow
python -m app.db.seed

Write-Host "`n[4/5] DB checks..." -ForegroundColor Yellow
Set-Location ..
$catCount = (docker-compose exec -T db psql -U finance -d finance -tAc "SELECT count(*) FROM categories;").Trim()
$ruleCount = (docker-compose exec -T db psql -U finance -d finance -tAc "SELECT count(*) FROM merchant_rules;").Trim()
$tableCount = (docker-compose exec -T db psql -U finance -d finance -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';").Trim()

Write-Host "  categories count: $catCount (expect >= 12)"
Write-Host "  merchant_rules count: $ruleCount (expect >= 25)"
Write-Host "  public table count: $tableCount (expect 9, includes alembic_version)"

if ([int]$catCount -lt 12) { throw "categories < 12" }
if ([int]$ruleCount -lt 25) { throw "merchant_rules < 25" }
if ([int]$tableCount -lt 9) { throw "table count < 9" }

Write-Host "`n[5/5] pytest..." -ForegroundColor Yellow
Set-Location backend
pytest -q

Set-Location ..
Write-Host "`n=== Slice A DoD: ALL PASS ===" -ForegroundColor Green
