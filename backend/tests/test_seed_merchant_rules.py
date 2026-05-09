"""种子商家规则 seed 测试。"""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.seed_categories import seed_default_categories
from app.db.seed_merchant_rules import seed_default_merchant_rules
from app.models import MerchantRule, User


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


def test_seed_rules_creates_at_least_25(db: Session, admin_user: User):
    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()
    seed_default_merchant_rules(db, default_user_id=admin_user.id)
    db.commit()

    rules = db.execute(select(MerchantRule)).scalars().all()
    assert len(rules) >= 25


def test_seed_rules_idempotent(db: Session, admin_user: User):
    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()
    seed_default_merchant_rules(db, default_user_id=admin_user.id)
    db.commit()
    first = db.execute(select(MerchantRule)).scalars().all()
    n = len(first)

    seed_default_merchant_rules(db, default_user_id=admin_user.id)
    db.commit()
    second = db.execute(select(MerchantRule)).scalars().all()

    assert len(second) == n


def test_seed_rules_priority_ordering(db: Session, admin_user: User):
    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()
    seed_default_merchant_rules(db, default_user_id=admin_user.id)
    db.commit()

    # priority 最低数字 = 最先匹配。"银联入账" 应该是最高优先级(priority=10)
    top_rule = db.execute(
        select(MerchantRule).order_by(MerchantRule.priority).limit(1)
    ).scalar_one()
    assert "银联入账" in top_rule.pattern or top_rule.priority <= 10
