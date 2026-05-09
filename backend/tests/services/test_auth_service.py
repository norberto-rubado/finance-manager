"""auth service 单元测试 — bcrypt + JWT。"""
import time

import pytest
from passlib.hash import bcrypt as bcrypt_hash

from app.services.auth import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    verify_password,
)


def test_verify_password_correct():
    h = bcrypt_hash.hash("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_password_wrong():
    h = bcrypt_hash.hash("hunter2")
    assert verify_password("nope", h) is False


def test_verify_password_invalid_hash_returns_false():
    """无效 hash 不应抛 raise,返回 False(防止 user enum 通过 5xx 区分)。"""
    assert verify_password("anything", "not_a_bcrypt") is False


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token(subject="admin", expires_minutes=15)
    payload = decode_access_token(token)
    assert payload["sub"] == "admin"
    assert "exp" in payload


def test_decode_expired_token_raises():
    """过期 token 必须 raise InvalidTokenError。"""
    token = create_access_token(subject="admin", expires_minutes=-1)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_tampered_token_raises():
    token = create_access_token(subject="admin", expires_minutes=10)
    bad = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    with pytest.raises(InvalidTokenError):
        decode_access_token(bad)


def test_decode_empty_or_garbage_raises():
    for bad in ["", "   ", "not.a.jwt", "x.y.z"]:
        with pytest.raises(InvalidTokenError):
            decode_access_token(bad)
