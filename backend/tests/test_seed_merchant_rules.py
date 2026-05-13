"""种子商家规则 seed 测试。"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.seed_categories import seed_default_categories
from app.db.seed_merchant_rules import seed_default_merchant_rules
from app.models import MerchantRule, User


@pytest.fixture
def fresh_user(db: Session) -> User:
    """每个测试独立的临时 user — 避开 dev db 中 admin 已 seed 的 rules。"""
    user = User(
        username=f"test_seed_{uuid.uuid4().hex[:8]}",
        password_hash="$2b$12$dummy",
    )
    db.add(user)
    db.flush()
    return user


EXPECTED_RULE_COUNT = 29  # 严格匹配种子表行数,参见 seed_default_merchant_rules._RULES


def test_seed_rules_creates_exact_count(db: Session, fresh_user: User):
    seed_default_categories(db, default_user_id=fresh_user.id)
    db.commit()
    created, total = seed_default_merchant_rules(db, default_user_id=fresh_user.id)
    db.commit()

    assert total == EXPECTED_RULE_COUNT
    assert created == EXPECTED_RULE_COUNT, "首次 seed,created 应等于全部"

    rules = db.execute(
        select(MerchantRule).where(MerchantRule.user_id == fresh_user.id)
    ).scalars().all()
    assert len(rules) == EXPECTED_RULE_COUNT


def test_seed_rules_idempotent(db: Session, fresh_user: User):
    seed_default_categories(db, default_user_id=fresh_user.id)
    db.commit()
    created1, total1 = seed_default_merchant_rules(db, default_user_id=fresh_user.id)
    db.commit()
    first = db.execute(
        select(MerchantRule).where(MerchantRule.user_id == fresh_user.id)
    ).scalars().all()

    created2, total2 = seed_default_merchant_rules(db, default_user_id=fresh_user.id)
    db.commit()
    second = db.execute(
        select(MerchantRule).where(MerchantRule.user_id == fresh_user.id)
    ).scalars().all()

    assert len(first) == len(second) == EXPECTED_RULE_COUNT
    assert created1 == EXPECTED_RULE_COUNT
    assert created2 == 0, "二次跑 created 必须为 0,否则误导运维"
    assert total1 == total2 == EXPECTED_RULE_COUNT


def test_seed_rules_priority_ordering(db: Session, fresh_user: User):
    seed_default_categories(db, default_user_id=fresh_user.id)
    db.commit()
    seed_default_merchant_rules(db, default_user_id=fresh_user.id)
    db.commit()

    # priority 最低数字 = 最先匹配。"银联入账" 应该是最高优先级(priority=10)
    top_rule = db.execute(
        select(MerchantRule)
        .where(MerchantRule.user_id == fresh_user.id)
        .order_by(MerchantRule.priority)
        .limit(1)
    ).scalar_one()
    assert "银联入账" in top_rule.pattern or top_rule.priority <= 10
