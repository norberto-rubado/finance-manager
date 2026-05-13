"""默认分类树 seed。幂等:按 (user_id, name, parent_id) 检查后插入。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category


# 树形结构:(name, kind, sort_order, [(child_name, sort_order), ...])
_TREE: list[tuple[str, str, int, list[tuple[str, int]]]] = [
    ("餐饮", "expense", 10, [
        ("咖啡", 11), ("早餐", 12), ("午餐", 13), ("晚餐", 14),
        ("外卖", 15), ("食材", 16), ("零食", 17),
    ]),
    ("交通", "expense", 20, [
        ("公交地铁", 21), ("打车", 22), ("加油", 23), ("停车", 24),
    ]),
    ("购物", "expense", 30, [
        ("淘宝", 31), ("京东", 32), ("拼多多", 33), ("实体店", 34),
    ]),
    ("通讯", "expense", 40, [("话费", 41), ("流量", 42)]),
    ("居家", "expense", 50, [
        ("房租", 51), ("水电气", 52), ("物业", 53),
    ]),
    ("娱乐", "expense", 60, [
        ("游戏", 61), ("视频会员", 62), ("阅读", 63), ("电影", 64), ("旅行", 65),
    ]),
    ("医疗", "expense", 70, []),
    ("职业", "expense", 80, [("会费", 81), ("学习", 82)]),
    ("转账", "expense", 90, [("红包", 91), ("个人转账", 92)]),

    ("工资", "income", 110, []),
    ("奖金", "income", 120, []),
    ("投资收益", "income", 130, []),
    ("退款", "income", 140, []),
    ("其他收入", "income", 150, []),

    ("内部转账", "neutral", 210, []),
    ("充值提现", "neutral", 220, []),
    ("信用卡还款入账", "neutral", 230, []),
]


def _get_or_create(
    db: Session, *, user_id: int, name: str, parent_id: int | None, kind: str, sort_order: int
) -> tuple[Category, bool]:
    """返回 (category, created)。created=True 表示本次新建。"""
    stmt = select(Category).where(
        Category.user_id == user_id,
        Category.name == name,
        Category.parent_id.is_(parent_id) if parent_id is None else Category.parent_id == parent_id,
    )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing, False
    cat = Category(
        user_id=user_id, name=name, parent_id=parent_id, kind=kind, sort_order=sort_order
    )
    db.add(cat)
    db.flush()
    return cat, True


def seed_default_categories(db: Session, default_user_id: int) -> tuple[int, int]:
    """seed 默认分类树。返回 (created, total)。

    created 是本次新建的分类行数(幂等二次跑 = 0),total 是种子定义里的总条目数。
    历史版本仅返回 total,二次跑误导运维以为"又插了 46 条"。
    """
    created = 0
    total = 0
    for top_name, kind, top_order, children in _TREE:
        top, was_created = _get_or_create(
            db, user_id=default_user_id, name=top_name, parent_id=None, kind=kind, sort_order=top_order
        )
        total += 1
        if was_created:
            created += 1
        for child_name, child_order in children:
            _, child_was_created = _get_or_create(
                db, user_id=default_user_id, name=child_name,
                parent_id=top.id, kind=kind, sort_order=child_order,
            )
            total += 1
            if child_was_created:
                created += 1
    return created, total
