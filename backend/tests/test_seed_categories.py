"""默认分类树 seed 测试:幂等 + 顶级分类齐全。"""
import pytest
from sqlalchemy.orm import Session

from app.db.seed_categories import seed_default_categories
from app.models import Category, User


@pytest.fixture
def admin_user(db: Session) -> User:
    """Idempotent: 不论 db 里有没有 admin,都返回该 user。

    用 ON CONFLICT 兼容 dev db 已有 admin 行的情况(savepoint 不能 rollback
    constraint violation)。
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = (
        pg_insert(User)
        .values(username="admin", password_hash="$2b$12$dummy")
        .on_conflict_do_nothing(index_elements=["username"])
    )
    db.execute(stmt)
    db.flush()
    return db.query(User).filter_by(username="admin").one()


def test_seed_creates_categories(db: Session, admin_user: User):
    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()

    cats = db.query(Category).all()
    assert len(cats) >= 12, "应有至少 12 个分类(顶级 + 二级若干)"

    top_names = {c.name for c in cats if c.parent_id is None}
    assert {"餐饮", "交通", "购物", "通讯", "工资", "内部转账"}.issubset(top_names)


def test_seed_categories_idempotent(db: Session, admin_user: User):
    """重复跑 seed 不应出现重复行。"""
    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()
    first_count = db.query(Category).count()

    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()
    second_count = db.query(Category).count()

    assert first_count == second_count
