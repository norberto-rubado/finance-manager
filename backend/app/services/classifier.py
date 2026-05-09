"""规则分类引擎 — spec § 7。

契约见 tests/services/test_classifier_marker_contract.py(Task 4 冻结):
- 普通规则命中:T.category_id = rule.category_id, confidence=1.0, hit_count++, break
- marker 规则命中(rule.category_id IS NULL):hit_count++, T.raw_payload['markers'] += pattern, NOT break
- 多 marker + 真规则:markers 累加 + 真规则赋值后 break
- 全 marker 命中:category_id 仍 None,markers 累加
"""
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import MerchantRule, Transaction


_FUZZY_THRESHOLD = 80


@dataclass
class ClassifyResult:
    """单条分类结果,Task 4 契约测试用 matched_rule_id。"""
    matched_rule_id: int | None
    matched_marker_ids: list[int] = field(default_factory=list)


def _match_rule(merchant_norm: str, pattern: str, match_kind: str) -> bool:
    """返回 merchant_normalized 是否命中规则 pattern。"""
    if not merchant_norm or not pattern:
        return False
    if match_kind == "exact":
        return merchant_norm == pattern
    if match_kind == "contains":
        return pattern.lower() in merchant_norm.lower()
    if match_kind == "regex":
        try:
            return re.search(pattern, merchant_norm) is not None
        except re.error:
            return False
    if match_kind == "fuzzy":
        return fuzz.WRatio(merchant_norm, pattern) >= _FUZZY_THRESHOLD
    return False


def _append_marker(tx: Transaction, pattern: str) -> None:
    """累加 pattern 到 tx.raw_payload['markers'],去重保持顺序。"""
    payload = dict(tx.raw_payload or {})
    markers: list[str] = list(payload.get("markers") or [])
    if pattern not in markers:
        markers.append(pattern)
    payload["markers"] = markers
    tx.raw_payload = payload
    flag_modified(tx, "raw_payload")


def classify_transaction(db: Session, tx: Transaction) -> ClassifyResult:
    """对单条交易跑规则匹配。spec § 7.2 + Task 4 契约。

    已分类(category_id 非 None)→ no-op,直接返回 ClassifyResult(None, [])。
    """
    if tx.category_id is not None:
        return ClassifyResult(matched_rule_id=None, matched_marker_ids=[])

    rules = db.execute(
        select(MerchantRule)
        .where(MerchantRule.user_id == tx.user_id)
        .order_by(MerchantRule.priority.asc(), MerchantRule.id.asc())
    ).scalars().all()

    matched_marker_ids: list[int] = []

    for rule in rules:
        if not _match_rule(tx.merchant_normalized or "", rule.pattern, rule.match_kind):
            continue
        rule.hit_count = (rule.hit_count or 0) + 1
        if rule.category_id is None:
            # marker 规则:不 break,继续找真分类
            _append_marker(tx, rule.pattern)
            matched_marker_ids.append(rule.id)
            continue
        # 真分类规则:赋值 + break
        tx.category_id = rule.category_id
        tx.classification_confidence = 1.0
        db.flush()
        return ClassifyResult(matched_rule_id=rule.id, matched_marker_ids=matched_marker_ids)

    db.flush()
    return ClassifyResult(matched_rule_id=None, matched_marker_ids=matched_marker_ids)


def classify_batch(
    db: Session, *, user_id: int, tx_ids: list[int],
) -> tuple[int, int]:
    """批量分类。返回 (classified_count, marker_only_count)。

    classified_count = 真分类生效的 tx 数(category_id 被赋值)
    marker_only_count = 仅命中 marker 但未被真分类的 tx 数
    """
    if not tx_ids:
        return 0, 0
    classified = 0
    marker_only = 0
    txs = db.execute(
        select(Transaction).where(
            Transaction.id.in_(tx_ids),
            Transaction.user_id == user_id,
        )
    ).scalars().all()
    for tx in txs:
        result = classify_transaction(db, tx)
        if result.matched_rule_id is not None:
            classified += 1
        elif result.matched_marker_ids:
            marker_only += 1
    db.flush()
    return classified, marker_only
