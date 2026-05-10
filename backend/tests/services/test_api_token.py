"""API token service:生成 / 哈希 / 验证 / 吊销。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import ApiToken, User
from app.services.api_token import (
    create_api_token, hash_token, list_tokens, revoke_token, verify_token,
)


@pytest.fixture
def user(db) -> User:
    u = User(username="token_test", password_hash="$2b$12$x" + "y" * 50)
    db.add(u); db.flush(); return u


def test_create_returns_plain_and_persists_hash(db, user):
    """create_api_token 返回 (token_obj, plain_token) — plain 仅出现这一次。"""
    plain, token_obj = create_api_token(db, user_id=user.id, name="my MCP token")
    assert isinstance(plain, str)
    assert len(plain) >= 32  # secrets.token_urlsafe(32) ≈ 43 字符
    assert token_obj.id is not None
    assert token_obj.user_id == user.id
    assert token_obj.name == "my MCP token"
    assert token_obj.scopes == "read,write"
    assert token_obj.revoked_at is None
    # token_hash 是 hash,不是明文
    assert token_obj.token_hash != plain
    assert token_obj.token_hash == hash_token(plain)


def test_hash_token_is_deterministic_and_64_chars(db):
    """sha256 hex digest = 64 chars,同输入同输出。"""
    h1 = hash_token("abc")
    h2 = hash_token("abc")
    assert h1 == h2
    assert len(h1) == 64
    assert h1 != hash_token("abd")


def test_verify_token_success_updates_last_used_at(db, user):
    plain, _ = create_api_token(db, user_id=user.id, name="t1")
    before = datetime.now(timezone.utc)

    verified_user = verify_token(db, plain)
    assert verified_user is not None
    assert verified_user.id == user.id

    # last_used_at 已被更新
    token_obj = db.execute(select(ApiToken).where(ApiToken.user_id == user.id)).scalar_one()
    assert token_obj.last_used_at is not None
    assert token_obj.last_used_at >= before


def test_verify_token_unknown_returns_none(db):
    """乱给的 token → None,不抛异常。"""
    result = verify_token(db, "definitely-not-a-real-token")
    assert result is None


def test_verify_token_revoked_returns_none(db, user):
    plain, token_obj = create_api_token(db, user_id=user.id, name="t1")
    revoke_token(db, token_id=token_obj.id, user_id=user.id)
    assert verify_token(db, plain) is None


def test_revoke_token_idempotent(db, user):
    plain, token_obj = create_api_token(db, user_id=user.id, name="t1")
    revoke_token(db, token_id=token_obj.id, user_id=user.id)
    first_revoked_at = token_obj.revoked_at
    revoke_token(db, token_id=token_obj.id, user_id=user.id)
    # revoked_at 不被覆盖(保留最早撤销时间)
    db.refresh(token_obj)
    assert token_obj.revoked_at == first_revoked_at


def test_revoke_token_other_user_denied(db, user):
    """A 用户不能撤销 B 用户的 token。"""
    other = User(username="other_token_test", password_hash="$2b$12$x" + "z" * 50)
    db.add(other); db.flush()
    plain, token_obj = create_api_token(db, user_id=other.id, name="other-token")
    # user 来撤 other 的 token → False(没找到)
    result = revoke_token(db, token_id=token_obj.id, user_id=user.id)
    assert result is False
    # other 的 token 仍可用
    db.refresh(token_obj)
    assert token_obj.revoked_at is None


def test_list_tokens_excludes_other_users_and_orders_by_created_at_desc(db, user):
    plain1, t1 = create_api_token(db, user_id=user.id, name="alpha")
    plain2, t2 = create_api_token(db, user_id=user.id, name="beta")
    other = User(username="other_list_test", password_hash="$2b$12$x" + "w" * 50)
    db.add(other); db.flush()
    create_api_token(db, user_id=other.id, name="other")

    rows = list_tokens(db, user_id=user.id)
    assert [r.name for r in rows] == ["beta", "alpha"]  # DESC by created_at
    # 没有 other 的 token
    assert all(r.user_id == user.id for r in rows)
