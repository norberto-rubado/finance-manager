# VPS 一键部署 cheatsheet — Finance Manager MVP

适用:Debian 12 / Ubuntu 22.04 LTS,4 GB RAM 以上,根用户或有 sudo 的 user。

## 1. 系统准备

```bash
# 包仓库 + 时间同步
apt-get update && apt-get -y upgrade
apt-get -y install ca-certificates curl gnupg ufw fail2ban age rclone unattended-upgrades

# Docker(官方仓库)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-compose
```

注意:`docker-compose`(v1,横线版)和 `docker compose`(v2 plugin)二者并存。MVP **用 v1 横线版**(`apt install docker-compose`),与 CLAUDE.md 约定一致。

## 2. 防火墙(spec § 11.5)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 8443/tcp comment 'finance-manager web (Caddy)'
ufw allow 9443/tcp comment 'finance-manager mcp (Caddy)'
ufw enable
ufw status verbose
```

`fail2ban` 默认配置已护 SSH;无需改 jail.local。

## 3. SSH 加固

```bash
# 编辑 /etc/ssh/sshd_config:
#   PasswordAuthentication no
#   PermitRootLogin no       # 如果上面已用根用户,先建 sudo user 再禁
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh
```

## 4. 拉代码 + .env

```bash
mkdir -p /opt && cd /opt
git clone <your-repo-url> finance-manager
cd finance-manager

# .env 从 .env.example 拷贝,填真实值
cp .env.example .env
chmod 0600 .env
nano .env
```

需要填的字段(spec § 14):

| 字段 | 怎么生成 |
|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -hex 16` |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `ADMIN_USERNAME` | 自定 |
| `ADMIN_PASSWORD_HASH` | `docker run --rm python:3.11-slim sh -c "pip install -q passlib bcrypt && python -c \"from passlib.hash import bcrypt; print(bcrypt.hash('YOUR_DEV_PASSWORD'))\""` |
| `MCP_API_TOKEN` | 部署后在 web /api/admin/tokens 端点生成,**不**在 .env 预填(留空字符串占位) |
| `DOMAIN` | `money.yourdomain.com`(已绑 Cloudflare) |
| `CLOUDFLARE_API_TOKEN` | Cloudflare → My Profile → API Tokens → 新建 token,scope: `Zone.DNS:Edit` ONLY |
| `CADDY_ACME_EMAIL` | 你收 Let's Encrypt 通知的邮箱 |

## 5. 启动 prod profile

```bash
cd /opt/finance-manager
docker-compose --profile prod up -d --build
docker-compose --profile prod ps
docker-compose --profile prod logs -f caddy   # 看 cert 是否签发成功
```

期望 Caddy 日志含 `certificate obtained successfully` 或 `serving initial configuration` 类提示。

测试访问:

```bash
curl -I https://${DOMAIN}:8443/api/health
# 期望 200,JSON {"status":"ok","db":"ok"}
```

## 6. 创建首个 admin user + MCP token

```bash
# 进 backend container 跑 seed(创 admin)
docker exec -it finance-manager-backend-prod python -m app.db.seed
# (seed 已读 .env 的 ADMIN_USERNAME / ADMIN_PASSWORD_HASH)

# 浏览器登录 https://${DOMAIN}:8443 → settings → 创建 token
# 或 curl:
SESSION=$(curl -s -c - https://${DOMAIN}:8443/api/auth/login -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"YOUR_DEV_PASSWORD"}' | grep fm_session | awk '{print $7}')
TOKEN=$(curl -s https://${DOMAIN}:8443/api/admin/tokens \
    -H "Cookie: fm_session=$SESSION" -H 'Content-Type: application/json' \
    -d '{"name":"prod-mcp"}' | jq -r .plain_token)

# 把 TOKEN 写回 .env 的 MCP_API_TOKEN,重启 mcp service
sed -i "s|^MCP_API_TOKEN=.*|MCP_API_TOKEN=$TOKEN|" .env
docker-compose --profile prod up -d mcp_prod
```

## 7. 备份配置

```bash
# 7.1 装 age 密钥(生成一对,公钥放 VPS,私钥保留本地)
# 本地机器:
age-keygen -o ~/finance-manager-backup.key
# 把生成的 age1... 公钥贴到 VPS 的 /etc/finance-manager.backup.env

# 7.2 配 rclone R2 remote(VPS 上一次性互动配)
rclone config
# 选 New remote 名 'r2'
# Storage: Cloudflare R2
# Access Key ID / Secret: 在 Cloudflare R2 → Manage R2 API Tokens 创建

# 7.3 backup env file
cat > /etc/finance-manager.backup.env <<EOF
AGE_RECIPIENT=age1xxxxxxxxxxxxxxxxxxxx
R2_BUCKET=finance-backups
POSTGRES_USER=finance
POSTGRES_DB=finance
EOF
chmod 0600 /etc/finance-manager.backup.env

# 7.4 cron
crontab -e
# 加一行:
0 3 * * * /opt/finance-manager/scripts/backup.sh >> /var/log/fm-backup.log 2>&1
```

dry-run 测一次:

```bash
/opt/finance-manager/scripts/backup.sh
# 期望日志含 "[fm-backup ...] daily upload OK"
# 验证 R2:
rclone ls r2:finance-backups/daily/
```

## 8. 解密恢复(灾难恢复演练)

**在本地机器**(私钥不离本地):

```bash
rclone copy r2:finance-backups/daily/finance-20260510.sql.age ./
age -d -i ~/finance-manager-backup.key finance-20260510.sql.age > restore.sql
# 在 VPS 上:
docker exec -i finance-manager-db-prod psql -U finance -d finance < restore.sql
```

## 9. 自动安全更新(unattended-upgrades)

```bash
dpkg-reconfigure --priority=low unattended-upgrades
# 选 "Yes" 启用 daily security upgrades
```

## 10. 升级流程

```bash
cd /opt/finance-manager
git pull
docker-compose --profile prod up -d --build
# alembic migration 在 backend_prod 启动 command 里 auto-run
```

## 故障排查

| 症状 | 排查 |
|---|---|
| Caddy 日志反复 "obtaining certificate" 失败 | 检查 `CLOUDFLARE_API_TOKEN` scope 是否有 Zone.DNS:Edit |
| `https://domain:8443` 502 Bad Gateway | `docker-compose ps` 看 backend_prod 是否 healthy;`docker logs finance-manager-backend-prod` |
| MCP 调用 401 | token 不匹配:`docker exec finance-manager-mcp-prod sh -c 'echo $MCP_API_TOKEN | head -c 20'` 与 db 中 token_hash 是否同一来源 |
| pg_dump 备份 0 字节 | `docker exec finance-manager-db-prod pg_isready` 验 db 在跑;`docker logs` 看 db 内有无错 |
