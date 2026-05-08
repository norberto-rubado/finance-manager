"""seed 主入口:可被 CLI 或测试调用。"""
import sys
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import db_session
from app.models import User
from app.db.seed_categories import seed_default_categories


def ensure_default_user(db: Session) -> User:
    """确保 admin 用户存在(幂等)。"""
    existing = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
    if existing:
        return existing
    user = User(
        username="admin",
        password_hash="$2b$12$placeholder_replace_in_slice_c",  # 切片 C 真正做认证时改
    )
    db.add(user)
    db.flush()
    return user


def run_seed() -> None:
    with db_session() as db:
        user = ensure_default_user(db)
        cat_count = seed_default_categories(db, default_user_id=user.id)
        print(f"[seed] user_id={user.id}, categories seeded={cat_count}")


if __name__ == "__main__":
    run_seed()
    sys.exit(0)
