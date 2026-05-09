"""seed.ensure_default_user 测试 — 真 hash 注入 + 幂等 + 改密更新。"""
import pytest
from sqlalchemy import select

from app.db.seed import ensure_default_user
from app.models import User


def test_seed_user_creates_with_settings_hash(db, monkeypatch):
    """初次跑:用 Settings.admin_password_hash 创建。"""
    fake_hash = "$2b$12$" + "x" * 53  # 60 字符,bcrypt 标准长度
    fake_username = "admin"

    # 通过 monkeypatch Settings 暴露的 getter
    from app.core import config as cfg_mod
    cfg_mod.get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_USERNAME", fake_username)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", fake_hash)

    user = ensure_default_user(db)
    db.flush()
    assert user.username == fake_username
    assert user.password_hash == fake_hash


def test_seed_user_idempotent_same_hash(db, monkeypatch):
    """二次跑:已存在 admin 且 hash 相同 → 不变。"""
    fake_hash = "$2b$12$" + "y" * 53
    from app.core import config as cfg_mod
    cfg_mod.get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", fake_hash)

    u1 = ensure_default_user(db)
    db.flush()
    u2 = ensure_default_user(db)
    db.flush()
    assert u1.id == u2.id
    assert u2.password_hash == fake_hash


def test_seed_user_updates_hash_when_env_changes(db, monkeypatch):
    """改密场景:.env 换 hash 后,re-seed 应同步更新数据库行(避免登录失败)。"""
    from app.core import config as cfg_mod

    cfg_mod.get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$" + "a" * 53)
    u1 = ensure_default_user(db)
    db.flush()
    old_hash = u1.password_hash

    cfg_mod.get_settings.cache_clear()
    new_hash = "$2b$12$" + "b" * 53
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", new_hash)
    u2 = ensure_default_user(db)
    db.flush()
    assert u1.id == u2.id
    assert u2.password_hash == new_hash
    assert old_hash != new_hash


def test_seed_user_rejects_obvious_placeholder(db, monkeypatch):
    """防御:仍是 slice A 占位符 hash → 抛 ValueError 拦截配置错。"""
    from app.core import config as cfg_mod

    cfg_mod.get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$placeholder_replace_in_slice_c")
    with pytest.raises(ValueError, match="placeholder"):
        ensure_default_user(db)
