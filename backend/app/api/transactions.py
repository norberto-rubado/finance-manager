"""Transactions API — spec § 9.1 + § 8.1 部分写工具的 REST 等价。"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from app.api.deps import CurrentUserDep, DbDep
from app.models import Category, MerchantRule, Transaction
from app.schemas import (
    BulkUpdateByMerchantIn, BulkUpdateResult,
    TransactionListOut, TransactionOut, TransactionPatchIn, TransactionQuery,
)


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=TransactionListOut)
def list_transactions(
    user: CurrentUserDep, db: DbDep,
    q: Annotated[TransactionQuery, Depends()],
) -> TransactionListOut:
    """spec § 9.1。query 用 Pydantic 模型,FastAPI 把 query string 装到 q。"""
    conds = [Transaction.user_id == user.id]
    if q.date_from is not None:
        conds.append(Transaction.tx_time >= q.date_from)
    if q.date_to is not None:
        conds.append(Transaction.tx_time <= q.date_to)
    if q.account_id is not None:
        conds.append(Transaction.account_id == q.account_id)
    if q.category_id is not None:
        conds.append(Transaction.category_id == q.category_id)
    if q.kind is not None:
        conds.append(Transaction.tx_kind == q.kind)
    if q.source is not None:
        conds.append(Transaction.source == q.source)
    if q.is_mirror is not None:
        conds.append(Transaction.is_mirror == q.is_mirror)
    if q.keyword:
        conds.append(Transaction.merchant_normalized.ilike(f"%{q.keyword}%"))

    where = and_(*conds)
    total = db.execute(select(func.count()).select_from(Transaction).where(where)).scalar_one()
    items = db.execute(
        select(Transaction).where(where)
        .order_by(Transaction.tx_time.desc(), Transaction.id.desc())
        .limit(q.limit).offset(q.offset)
    ).scalars().all()
    return TransactionListOut(
        items=[TransactionOut.model_validate(t) for t in items],
        total=total, limit=q.limit, offset=q.offset,
    )


def _get_tx_or_404(db, user_id: int, tx_id: int) -> Transaction:
    tx = db.execute(
        select(Transaction).where(
            Transaction.id == tx_id, Transaction.user_id == user_id,
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "transaction not found")
    return tx


@router.get("/{tx_id}", response_model=TransactionOut)
def get_transaction(tx_id: int, user: CurrentUserDep, db: DbDep) -> TransactionOut:
    return TransactionOut.model_validate(_get_tx_or_404(db, user.id, tx_id))


@router.patch("/{tx_id}", response_model=TransactionOut)
def patch_transaction(
    tx_id: int, body: TransactionPatchIn, user: CurrentUserDep, db: DbDep,
) -> TransactionOut:
    tx = _get_tx_or_404(db, user.id, tx_id)
    if body.category_id is not None:
        cat = db.execute(
            select(Category).where(
                Category.id == body.category_id, Category.user_id == user.id,
            )
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
        tx.category_id = body.category_id
        tx.classification_confidence = 1.0  # 用户手工 = 完全确信
    if body.tx_kind is not None:
        tx.tx_kind = body.tx_kind
    db.flush()
    return TransactionOut.model_validate(tx)


@router.post("/bulk-update-by-merchant", response_model=BulkUpdateResult)
def bulk_update_by_merchant(
    body: BulkUpdateByMerchantIn, user: CurrentUserDep, db: DbDep,
) -> BulkUpdateResult:
    """spec § 8.1 同款。先在内存层用 classifier._match_rule 选 tx,
    再批量 UPDATE,可选加规则(同 user/pattern/match_kind 已有则复用)。"""
    cat = db.execute(
        select(Category).where(
            Category.id == body.category_id, Category.user_id == user.id,
        )
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")

    # 选所有 user 的 tx,按 match_kind 在 Python 端过滤(简单稳妥)
    from app.services.classifier import _match_rule
    all_txs = db.execute(
        select(Transaction).where(Transaction.user_id == user.id)
    ).scalars().all()
    affected = 0
    for tx in all_txs:
        if _match_rule(tx.merchant_normalized or "", body.pattern, body.match_kind):
            tx.category_id = body.category_id
            tx.classification_confidence = 1.0
            affected += 1

    rule_id: int | None = None
    if body.also_add_rule:
        existing = db.execute(
            select(MerchantRule).where(
                MerchantRule.user_id == user.id,
                MerchantRule.pattern == body.pattern,
                MerchantRule.match_kind == body.match_kind,
            )
        ).scalar_one_or_none()
        if existing is None:
            rule = MerchantRule(
                user_id=user.id, pattern=body.pattern, match_kind=body.match_kind,
                category_id=body.category_id, priority=70,  # 用户加 priority 70(种子之间)
            )
            db.add(rule); db.flush()
            rule_id = rule.id
        else:
            existing.category_id = body.category_id
            rule_id = existing.id
    db.flush()
    return BulkUpdateResult(affected_count=affected, rule_id=rule_id)


@router.delete("/{tx_id}", status_code=204)
def delete_transaction(tx_id: int, user: CurrentUserDep, db: DbDep) -> None:
    """仅 source ∈ {conversation, manual} 允许删,避免删除账单原始数据。"""
    tx = _get_tx_or_404(db, user.id, tx_id)
    if tx.source not in ("conversation", "manual"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"cannot delete tx from source={tx.source!r}; "
            "delete originating statement_import instead (V2 feature)",
        )
    db.delete(tx)
    db.flush()
    return None
