#!/usr/bin/env bash
# scripts/backup.sh — finance-manager Postgres 加密备份 + 上传 R2。
# spec § 11.4。crontab: 0 3 * * * /opt/finance-manager/scripts/backup.sh
#
# 依赖(VPS 上 apt 装):
#   - docker / docker-compose
#   - age >= 1.0 (apt: age 或 brew install age)
#   - rclone >= 1.60(配 R2 remote 名 'r2',bucket = $R2_BUCKET)
#
# 必填环境变量(写在 /etc/finance-manager.backup.env,chmod 0600,owner root):
#   AGE_RECIPIENT  — 接收方公钥(age1...)
#   R2_BUCKET      — Cloudflare R2 bucket name
#   POSTGRES_USER  — db 用户(同 .env)
#   POSTGRES_DB    — db 名(同 .env)
#
# 输出:每天写一个 finance-{YYYYMMDD}.sql.age 上传 r2:$R2_BUCKET/daily/
#       每月 1 号同时复制到 r2:$R2_BUCKET/monthly/
#       本地不留任何文件,仅日志。
#
set -euo pipefail

ENV_FILE=/etc/finance-manager.backup.env
[[ -r $ENV_FILE ]] && source "$ENV_FILE"

: "${AGE_RECIPIENT:?AGE_RECIPIENT is required}"
: "${R2_BUCKET:?R2_BUCKET is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

DATE_STAMP=$(date -u '+%Y%m%d')
TS_HUMAN=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
LOG_TAG="[fm-backup $TS_HUMAN]"

echo "$LOG_TAG starting"

# 1) pg_dump from container,管道直接给 age,不落盘
docker exec finance-manager-db-prod pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  | age -r "$AGE_RECIPIENT" \
  | rclone rcat "r2:${R2_BUCKET}/daily/finance-${DATE_STAMP}.sql.age" \
  --s3-no-check-bucket

echo "$LOG_TAG daily upload OK"

# 2) 月初(每月 1 号)同时归档到 monthly/
if [[ $(date -u +%d) == "01" ]]; then
    rclone copyto \
      "r2:${R2_BUCKET}/daily/finance-${DATE_STAMP}.sql.age" \
      "r2:${R2_BUCKET}/monthly/finance-${DATE_STAMP}.sql.age" \
      --s3-no-check-bucket
    echo "$LOG_TAG monthly archive OK"
fi

# 3) 清 30 天前的 daily(R2 lifecycle 也可做,这里 belt & suspenders)
THIRTY_AGO=$(date -u -d '30 days ago' '+%Y%m%d')
rclone delete "r2:${R2_BUCKET}/daily/" \
  --include "finance-*.sql.age" \
  --max-age 30d \
  --s3-no-check-bucket || true

# 4) 清 12 个月前的 monthly
TWELVE_MO_AGO=$(date -u -d '12 months ago' '+%Y%m%d')
rclone delete "r2:${R2_BUCKET}/monthly/" \
  --include "finance-*.sql.age" \
  --max-age 365d \
  --s3-no-check-bucket || true

echo "$LOG_TAG done"
