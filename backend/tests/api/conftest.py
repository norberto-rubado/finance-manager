"""api 测试共享 fixture — TestClient + 已登录 client。"""
import pytest
from fastapi.testclient import TestClient
from passlib.hash import bcrypt as bcrypt_hash
from sqlalchemy import select

from app.core.db import get_db  # 同一函数对象,与 app/api/deps.py 共用
from app.main import app
from app.models import User


_TEST_PASSWORD = "test-pwd-2026"
_TEST_USERNAME = "admin"


@pytest.fixture
def admin_user(db) -> User:
    """确保 admin 存在 + password_hash 跟 _TEST_PASSWORD 对得上(覆盖 .env 的真实 hash)。"""
    user = db.execute(select(User).where(User.username == _TEST_USERNAME)).scalar_one_or_none()
    h = bcrypt_hash.hash(_TEST_PASSWORD)
    if user is None:
        user = User(username=_TEST_USERNAME, password_hash=h)
        db.add(user)
        db.flush()
    else:
        user.password_hash = h
        db.flush()
    return user


@pytest.fixture
def client(db) -> TestClient:
    """绑定 db fixture 的 TestClient — override get_db 让端点用同一 session。"""
    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def logged_in_client(client, admin_user) -> TestClient:
    """已登录 client(cookie 已注入)。"""
    resp = client.post("/api/auth/login", json={
        "username": _TEST_USERNAME,
        "password": _TEST_PASSWORD,
    })
    assert resp.status_code == 200, resp.text
    return client
