"""seed 主入口:可被 CLI 或测试调用。"""
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import db_session
from app.db.seed_categories import seed_default_categories
from app.db.seed_merchant_rules import seed_default_merchant_rules
from app.models import User


_PLACEHOLDER_TOKEN = "placeholder"


def _validate_bcrypt_hash(h: str) -> None:
    """防御性校验:hash 形如 $2b$XX$... 且不含 placeholder 字样。"""
    if not h or _PLACEHOLDER_TOKEN in h:
        raise ValueError(
            "ADMIN_PASSWORD_HASH is a placeholder -- generate a real bcrypt hash and put it in .env "
            "(see plan slice C Pre-flight for the one-liner)"
        )
    if not h.startswith(("$2a$", "$2b$", "$2y$")):
        raise ValueError(
            f"ADMIN_PASSWORD_HASH does not look like a bcrypt hash (got prefix={h[:6]!r}); "
            "expected $2a$/$2b$/$2y$..."
        )


def ensure_default_user(db: Session) -> User:
    """确保 admin 用户存在,且 password_hash 与 .env 一致(幂等 + 改密同步)。

    spec section 10.1 单用户硬编码:用户名/密码 hash 来自 .env。
    """
    settings = get_settings()
    username = settings.admin_username
    target_hash = settings.admin_password_hash
    _validate_bcrypt_hash(target_hash)

    existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing is None:
        user = User(username=username, password_hash=target_hash)
        db.add(user)
        db.flush()
        return user

    if existing.password_hash != target_hash:
        # .env 已改密 -> 同步更新,避免登录持续失败
        existing.password_hash = target_hash
        db.flush()
    return existing


def run_seed() -> None:
    with db_session() as db:
        user = ensure_default_user(db)
        cat_created, cat_total = seed_default_categories(db, default_user_id=user.id)
        rule_created, rule_total = seed_default_merchant_rules(db, default_user_id=user.id)
        print(
            f"[seed] user_id={user.id}, "
            f"categories: {cat_created} new / {cat_total} total, "
            f"rules: {rule_created} new / {rule_total} total"
        )


if __name__ == "__main__":
    run_seed()
    sys.exit(0)
