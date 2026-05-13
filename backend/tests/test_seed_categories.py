"""默认分类树 seed 测试:幂等 + 顶级分类齐全。"""
import uuid

import pytest
from sqlalchemy.orm import Session

from app.db.seed_categories import seed_default_categories
from app.models import Category, User


@pytest.fixture
def fresh_user(db: Session) -> User:
    """每个测试独立的临时 user — 避开 dev db 中 admin 已 seed 的 categories,
    才能断言 created/total 不变量(否则 created 永远是 0)。
    nested savepoint 会在测试结束 rollback,临时 user 不污染 dev db。
    """
    user = User(
        username=f"test_seed_{uuid.uuid4().hex[:8]}",
        password_hash="$2b$12$dummy",
    )
    db.add(user)
    db.flush()
    return user


EXPECTED_CATEGORY_COUNT = 46  # 9 expense 顶级 + 29 expense leaf + 5 income + 3 neutral


def test_seed_creates_categories(db: Session, fresh_user: User):
    created, total = seed_default_categories(db, default_user_id=fresh_user.id)
    db.commit()

    assert total == EXPECTED_CATEGORY_COUNT
    assert created == EXPECTED_CATEGORY_COUNT, "首次 seed,created 应等于全部"

    cats = db.query(Category).filter(Category.user_id == fresh_user.id).all()
    assert len(cats) == EXPECTED_CATEGORY_COUNT

    top_names = {c.name for c in cats if c.parent_id is None}
    assert {"餐饮", "交通", "购物", "通讯", "工资", "内部转账"}.issubset(top_names)


def test_seed_categories_idempotent(db: Session, fresh_user: User):
    """重复跑 seed 不应出现重复行,且 created 应反映"未新增"。"""
    created1, total1 = seed_default_categories(db, default_user_id=fresh_user.id)
    db.commit()
    first_count = db.query(Category).filter(Category.user_id == fresh_user.id).count()

    created2, total2 = seed_default_categories(db, default_user_id=fresh_user.id)
    db.commit()
    second_count = db.query(Category).filter(Category.user_id == fresh_user.id).count()

    assert first_count == second_count == EXPECTED_CATEGORY_COUNT
    assert created1 == EXPECTED_CATEGORY_COUNT
    assert created2 == 0, "二次跑 created 必须为 0,否则误导运维"
    assert total1 == total2 == EXPECTED_CATEGORY_COUNT
