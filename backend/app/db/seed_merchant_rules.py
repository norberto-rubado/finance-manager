"""种子商家规则。priority 越小越先匹配。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, MerchantRule


# (pattern, match_kind, category_path, priority)
# category_path:用 "/" 分隔的分类路径,seed 时解析到具体 category_id;None 表示规则只做"识别标记",不分类
_RULES: list[tuple[str, str, str | None, int]] = [
    # 优先级 10:跨源镜像/还款识别
    (r"银联入账.*\d{4}", "regex", "信用卡还款入账", 10),

    # 优先级 20:跨源中转方关键词标记(category=None,只起标记作用,真正分类靠对侧已分类)
    ("财付通-", "contains", None, 20),
    ("支付宝-", "contains", None, 20),
    ("蚂蚁(杭州)", "contains", None, 20),
    ("蚂蚁(中国)", "contains", None, 20),
    ("拉扎斯网络科技", "contains", None, 20),  # 饿了么
    ("云闪付", "contains", None, 20),
    ("支付平台", "contains", None, 25),

    # 优先级 30:用户身份相关(专利代理人)
    ("中华全国专利代理师协会", "contains", "职业/会费", 30),

    # 优先级 50:常见商家分类
    ("瑞幸咖啡", "fuzzy", "餐饮/咖啡", 50),
    ("luckin coffee", "fuzzy", "餐饮/咖啡", 50),
    ("luckincoffee", "contains", "餐饮/咖啡", 50),
    ("星巴克", "fuzzy", "餐饮/咖啡", 50),
    ("中国移动", "contains", "通讯/话费", 50),
    ("中国联通", "contains", "通讯/话费", 50),
    ("中国电信", "contains", "通讯/话费", 50),
    ("美团", "fuzzy", "餐饮/外卖", 50),
    ("淘宝平台商户", "contains", "购物/淘宝", 50),
    ("淘宝(中国)", "contains", "购物/淘宝", 50),
    ("京东商城", "contains", "购物/京东", 50),
    ("拼多多", "contains", "购物/拼多多", 50),
    ("起点中文网", "contains", "娱乐/阅读", 50),
    ("上海玄霆娱乐", "contains", "娱乐/阅读", 50),  # 起点母公司
    ("北京月之暗面科技", "contains", "娱乐/游戏", 50),  # Kimi 的母公司,可调整
    ("哔哩哔哩", "contains", "娱乐/视频会员", 50),
    ("爱奇艺", "contains", "娱乐/视频会员", 50),
    ("腾讯视频", "contains", "娱乐/视频会员", 50),

    # 优先级 60:微信红包/转账
    ("微信红包-单发", "exact", "转账/红包", 60),
    ("微信转账", "contains", "转账/个人转账", 60),
]


def _resolve_category_id(db: Session, user_id: int, path: str) -> int | None:
    """把 '餐饮/咖啡' 解析为 category_id。"""
    parts = path.split("/")
    parent_id: int | None = None
    cat: Category | None = None
    for part in parts:
        stmt = select(Category).where(
            Category.user_id == user_id,
            Category.name == part,
            (Category.parent_id == parent_id) if parent_id is not None else Category.parent_id.is_(None),
        )
        cat = db.execute(stmt).scalar_one_or_none()
        if cat is None:
            return None
        parent_id = cat.id
    return cat.id if cat else None


def seed_default_merchant_rules(db: Session, default_user_id: int) -> tuple[int, int]:
    """seed 种子规则。幂等:(user_id, pattern, match_kind) 唯一。

    返回 (created, total) — created 是本次新增数,total 是种子定义里的总条目数。
    与 seed_default_categories 的契约对齐,便于 run_seed 统一打印 "N new / M total"。
    """
    created = 0
    total = 0
    for pattern, match_kind, cat_path, priority in _RULES:
        total += 1
        # 幂等检查
        stmt = select(MerchantRule).where(
            MerchantRule.user_id == default_user_id,
            MerchantRule.pattern == pattern,
            MerchantRule.match_kind == match_kind,
        )
        if db.execute(stmt).scalar_one_or_none() is not None:
            continue

        category_id = _resolve_category_id(db, default_user_id, cat_path) if cat_path else None
        rule = MerchantRule(
            user_id=default_user_id,
            pattern=pattern,
            match_kind=match_kind,
            category_id=category_id,
            priority=priority,
        )
        db.add(rule)
        created += 1
    db.flush()
    return created, total
