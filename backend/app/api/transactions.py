"""Transactions API — spec § 9.1 + § 8.1 部分写工具的 REST 等价。"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from app.api.deps import CurrentUserDep, DbDep
from app.models import Account, Category, MerchantRule, Transaction
from app.schemas import (
    BulkUpdateByMerchantIn, BulkUpdateResult,
    MerchantSearchOut, MerchantStatItem,
    TransactionCreateIn, TransactionListOut, TransactionOut,
    TransactionPatchIn, TransactionQuery,
)
from app.services.classifier import classify_transaction
from app.services.statement_parser.normalize import normalize_merchant


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


@router.post("/manual", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_manual_transaction(
    body: TransactionCreateIn, user: CurrentUserDep, db: DbDep,
) -> TransactionOut:
    """spec § 8.1 add_transaction 工具的 backend 实现。

    流程:
    1) 校验 account_id 属于当前 user(404)
    2) 若给了 category_id → 校验属于当前 user(404),并跳过分类引擎
    3) 否则 → 跑 classify_transaction 单条,命中真规则填 category_id + confidence=1.0
    4) tx 落库 source='manual',source_unique_key=None,is_mirror=False
    """
    # 1) account 校验
    acc = db.execute(
        select(Account).where(
            Account.id == body.account_id, Account.user_id == user.id,
        )
    ).scalar_one_or_none()
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")

    # 2) category 校验(若给了)
    if body.category_id is not None:
        cat = db.execute(
            select(Category).where(
                Category.id == body.category_id, Category.user_id == user.id,
            )
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")

    # 3) 构 Transaction(暂不 commit,先看是否要跑 classifier)
    merchant_norm = normalize_merchant(body.merchant)
    tx = Transaction(
        user_id=user.id,
        account_id=body.account_id,
        statement_import_id=None,
        tx_kind=body.tx_kind,
        tx_time=body.tx_time,
        post_time=None,
        amount=body.amount,
        currency=body.currency,
        amount_settled_cny=body.amount,  # manual 默认 CNY,无需折算
        merchant_raw=body.merchant,
        merchant_normalized=merchant_norm,
        counterparty_raw=None,
        description_raw=body.description,
        category_id=body.category_id,
        classification_confidence=1.0 if body.category_id is not None else None,
        source="manual",
        external_tx_id=None,
        external_merchant_id=None,
        payment_method_raw=None,
        is_mirror=False,
        mirror_of_id=None,
        source_unique_key=None,
        raw_payload=None,
    )
    db.add(tx); db.flush()

    # 4) 若没显式给 category,跑 classifier(单条用 classify_transaction,
    #    它接收 in-memory tx 直接 mutate;classify_batch 走 id 列表是另一种契约)
    if body.category_id is None:
        classify_transaction(db, tx)
        db.flush()

    return TransactionOut.model_validate(tx)


@router.get("/merchants", response_model=MerchantSearchOut)
def find_merchants(
    user: CurrentUserDep, db: DbDep,
    keyword: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(50, ge=1, le=200),
) -> MerchantSearchOut:
    """spec § 8.1 find_merchant 工具的 backend 实现。

    聚合 group by merchant_normalized,排除 is_mirror=True;
    sample_categories:对每组取 top 3 出现频次最高的 category name(无分类记 NULL → 跳过)。
    """
    # Step 1:聚合 count + sum
    rows = db.execute(
        select(
            Transaction.merchant_normalized,
            func.count(Transaction.id).label("cnt"),
            func.sum(Transaction.amount_settled_cny).label("amt"),
        )
        .where(
            Transaction.user_id == user.id,
            Transaction.is_mirror.is_(False),
            Transaction.merchant_normalized.ilike(f"%{keyword}%"),
        )
        .group_by(Transaction.merchant_normalized)
        .order_by(func.sum(Transaction.amount_settled_cny).desc())
        .limit(limit)
    ).all()

    if not rows:
        return MerchantSearchOut(items=[], total=0)

    # Step 2:对每个 normalized,查它的 top 3 categories
    normalized_names = [r[0] for r in rows if r[0] is not None]
    cat_rows = db.execute(
        select(
            Transaction.merchant_normalized,
            Category.name,
            func.count(Transaction.id).label("hit_cnt"),
        )
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.user_id == user.id,
            Transaction.is_mirror.is_(False),
            Transaction.merchant_normalized.in_(normalized_names),
        )
        .group_by(Transaction.merchant_normalized, Category.name)
        .order_by(Transaction.merchant_normalized, func.count(Transaction.id).desc())
    ).all()

    # 把 top 3 折叠到 dict[normalized, list[name]]
    samples: dict[str, list[str]] = {}
    for norm, name, _cnt in cat_rows:
        bucket = samples.setdefault(norm, [])
        if len(bucket) < 3:
            bucket.append(name)

    items = [
        MerchantStatItem(
            normalized=(norm or ""),
            count=cnt,
            total_amount=amt,
            sample_categories=samples.get(norm, []),
        )
        for norm, cnt, amt in rows
    ]
    return MerchantSearchOut(items=items, total=len(items))


@router.get("/pending-classifications", response_model=TransactionListOut)
def list_pending_classifications(
    user: CurrentUserDep, db: DbDep,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TransactionListOut:
    """spec § 8.1 list_pending_classifications 工具的 backend 实现。

    返回 category_id IS NULL 且 is_mirror=False 的交易,按 tx_time DESC 翻页。
    suggested_categories 字段 V2 加(rapidfuzz vs categories.name)。
    """
    where = (
        (Transaction.user_id == user.id)
        & (Transaction.category_id.is_(None))
        & (Transaction.is_mirror.is_(False))
    )
    total = db.execute(select(func.count()).select_from(Transaction).where(where)).scalar_one()
    items = db.execute(
        select(Transaction).where(where)
        .order_by(Transaction.tx_time.desc(), Transaction.id.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    return TransactionListOut(
        items=[TransactionOut.model_validate(t) for t in items],
        total=total, limit=limit, offset=offset,
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
