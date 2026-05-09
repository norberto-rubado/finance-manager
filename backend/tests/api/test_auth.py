"""认证端点 e2e 测试。"""


def test_login_success_sets_cookie(client, admin_user):
    resp = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "test-pwd-2026",
    })
    assert resp.status_code == 200
    assert "fm_session" in resp.cookies
    body = resp.json()
    assert body["username"] == "admin"


def test_login_wrong_password_401(client, admin_user):
    resp = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "wrong",
    })
    assert resp.status_code == 401


def test_login_unknown_user_401(client, admin_user):
    """未知用户应与密码错返回同样 401(无 user enum 区分)。"""
    resp = client.post("/api/auth/login", json={
        "username": "ghost",
        "password": "anything",
    })
    assert resp.status_code == 401


def test_me_requires_login(client):
    """无 cookie /me → 401。"""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_returns_user(logged_in_client):
    resp = logged_in_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_logout_clears_cookie(logged_in_client):
    resp = logged_in_client.post("/api/auth/logout")
    assert resp.status_code == 204
    # 之后再请求 /me 应 401
    resp2 = logged_in_client.get("/api/auth/me")
    assert resp2.status_code == 401


def test_login_validates_input(client):
    resp = client.post("/api/auth/login", json={"username": "", "password": "x"})
    assert resp.status_code == 422  # Pydantic 校验失败


def test_health_unaffected_by_auth(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
