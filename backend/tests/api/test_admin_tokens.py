"""POST/GET/DELETE /api/admin/tokens — cookie 认证保护。"""
from __future__ import annotations

from sqlalchemy import select

from app.models import ApiToken


def test_create_token_returns_plain_once(logged_in_client, db, admin_user):
    resp = logged_in_client.post("/api/admin/tokens", json={"name": "MCP server"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "plain_token" in data
    assert isinstance(data["plain_token"], str)
    assert len(data["plain_token"]) >= 32
    assert data["token"]["id"]
    assert data["token"]["name"] == "MCP server"
    assert data["token"]["scopes"] == "read,write"
    # plain_token 不在 token 子对象里(避免被序列化进 list)
    assert "plain_token" not in data["token"]
    # DB 中 hash 与 plain 不同
    saved = db.execute(select(ApiToken).where(ApiToken.id == data["token"]["id"])).scalar_one()
    assert saved.token_hash != data["plain_token"]


def test_list_tokens_returns_no_plain(logged_in_client, db, admin_user):
    """list 不返回明文(只能 create 时拿到一次)。"""
    logged_in_client.post("/api/admin/tokens", json={"name": "t1"})
    resp = logged_in_client.get("/api/admin/tokens")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    for t in items:
        assert "plain_token" not in t
        assert "token_hash" not in t       # hash 也不暴露
        assert "name" in t and "id" in t


def test_revoke_token(logged_in_client, db, admin_user):
    create = logged_in_client.post("/api/admin/tokens", json={"name": "to-revoke"})
    tid = create.json()["token"]["id"]
    resp = logged_in_client.delete(f"/api/admin/tokens/{tid}")
    assert resp.status_code == 204
    # 再 list 仍能见(soft delete + revoked_at)
    items = logged_in_client.get("/api/admin/tokens").json()["items"]
    revoked = next(t for t in items if t["id"] == tid)
    assert revoked["revoked_at"] is not None


def test_revoke_unknown_token_404(logged_in_client):
    resp = logged_in_client.delete("/api/admin/tokens/99999")
    assert resp.status_code == 404


def test_admin_tokens_requires_cookie(client):
    """没 cookie → 401(client fixture 不带 login)。"""
    resp = client.post("/api/admin/tokens", json={"name": "x"})
    assert resp.status_code == 401
    resp = client.get("/api/admin/tokens")
    assert resp.status_code == 401


def test_admin_tokens_verify_endpoint(logged_in_client, db, admin_user):
    """POST /api/admin/tokens/verify — 内部端点,Bearer 验证 token,返回 user info。"""
    create = logged_in_client.post("/api/admin/tokens", json={"name": "v1"})
    plain = create.json()["plain_token"]

    # 用 raw client 走 Bearer(不要 cookie)
    from app.api.deps import SESSION_COOKIE_NAME

    # 复用 logged_in_client 但去掉 cookie 走 Bearer
    logged_in_client.cookies.delete(SESSION_COOKIE_NAME)
    resp = logged_in_client.post(
        "/api/admin/tokens/verify",
        headers={"Authorization": f"Bearer {plain}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == admin_user.id
    assert data["username"] == admin_user.username
    assert "scopes" in data


def test_admin_tokens_verify_bad_token_401(client):
    resp = client.post(
        "/api/admin/tokens/verify",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_admin_tokens_verify_missing_header_401(client):
    resp = client.post("/api/admin/tokens/verify")
    assert resp.status_code == 401
