"""导入流水线编排 service — spec § 5.1。

本切片任务拆分:
- Task 8(本 task):file_sha256 / ensure_account_for_hint / ensure_statement_import
- Task 9:persist_raw_transactions
- Task 15:run_import_pipeline(总编排:parser → setup → persist → dedup → classify)
"""
import hashlib
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, StatementImport, Transaction
from app.schemas import ImportResponse
from app.services.classifier import classify_batch
from app.services.dedup import run_dedup_pass
from app.services.statement_parser import (
    AccountHint,
    ParseResult,
    RawTransaction,
    UnsupportedStatementError,
    normalize_merchant,
    route_and_parse,
)


class DuplicateImportError(ValueError):
    """同 file_hash 已导入过(spec § 5.1 step 2),HTTP 层转 409。"""


_TYPE_TO_DISPLAY = {
    "bank_debit": "借记卡",
    "bank_credit": "信用卡",
}


def file_sha256(data: bytes) -> str:
    """sha256(data) hexdigest,作为 statement_imports.file_hash。"""
    return hashlib.sha256(data).hexdigest()


def _auto_name(hint: AccountHint) -> str:
    """自动起账户名 — spec § 5.1.1。

    bank_*:{institution}{借记卡|信用卡} {last4}
    alipay/wechat:{institution}
    cash:现金
    """
    if hint.type in ("bank_debit", "bank_credit"):
        kind = _TYPE_TO_DISPLAY[hint.type]
        last4 = hint.last4 or "????"
        return f"{hint.institution}{kind} {last4}"
    if hint.type in ("alipay", "wechat"):
        return hint.institution
    return hint.institution or "现金"


def ensure_account_for_hint(db: Session, user_id: int, hint: AccountHint) -> Account:
    """按 (user_id, institution, last4) 找;命中复用,未命中按 hint 创建。spec § 5.1.1。

    支付宝/微信 last4=None,SQL 用 IS NULL 严格匹配。
    """
    if hint.last4 is not None:
        stmt = select(Account).where(
            Account.user_id == user_id,
            Account.institution == hint.institution,
            Account.last4 == hint.last4,
        )
    else:
        stmt = select(Account).where(
            Account.user_id == user_id,
            Account.institution == hint.institution,
            Account.last4.is_(None),
        )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing
    acc = Account(
        user_id=user_id,
        name=_auto_name(hint),
        type=hint.type,
        institution=hint.institution,
        last4=hint.last4,
        currency="CNY",
    )
    db.add(acc)
    db.flush()
    return acc


def ensure_statement_import(
    db: Session,
    *,
    user_id: int,
    account_id: int,
    source_type: str,
    filename: str,
    file_hash: str,
    parse_result: ParseResult,
) -> StatementImport:
    """落 statement_imports 一行;file_hash 重复时抛 DuplicateImportError。

    spec § 5.1 step 2-4。imported/deduped/classified counts 在管道末尾(Task 15)更新。
    """
    existing = db.execute(
        select(StatementImport).where(StatementImport.file_hash == file_hash)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateImportError(
            f"file already imported as statement_import.id={existing.id} "
            f"on {existing.imported_at.isoformat() if existing.imported_at else '?'}"
        )

    si = StatementImport(
        user_id=user_id,
        account_id=account_id,
        source_type=source_type,
        filename=filename,
        file_hash=file_hash,
        period_start=parse_result.period_start,
        period_end=parse_result.period_end,
        raw_row_count=parse_result.metadata.get("raw_row_count", len(parse_result.raw_transactions)),
        imported_count=0,
        deduped_count=0,
        classified_count=0,
    )
    db.add(si)
    db.flush()
    return si


# ---------------------------------------------------------------------------
# Task 9: persist_raw_transactions
# ---------------------------------------------------------------------------

_SOURCE_TYPE_TO_SOURCE = {
    "alipay_csv": "alipay",
    "wechat_xlsx": "wechat",
    "bank_pdf_bocom_debit": "bank",
    "bank_pdf_ccb_credit": "bank",
}


def _short_source(source_type: str) -> str:
    """source_type -> source 短名(spec § 4.1)。"""
    if source_type in _SOURCE_TYPE_TO_SOURCE:
        return _SOURCE_TYPE_TO_SOURCE[source_type]
    raise ValueError(f"unknown source_type: {source_type!r}")


def _synth_unique_key(
    source_short: str, statement_import_id: int, row_idx: int,
    merchant: str, amount, tx_time,
) -> str:
    """external_tx_id 缺失时合成 unique key。

    用 statement_import_id + row_idx 保证 file 内唯一,加 sha8 防 file 间罕见撞。
    """
    sig = f"{merchant}|{amount}|{tx_time.isoformat()}".encode()
    sha8 = hashlib.sha256(sig).hexdigest()[:8]
    return f"{source_short}:si{statement_import_id}:r{row_idx}:{sha8}"


def persist_raw_transactions(
    db: Session,
    *,
    user_id: int,
    account_id: int,
    statement_import_id: int,
    source_type: str,
    raw_transactions: Iterable[RawTransaction],
) -> tuple[int, int]:
    """把 RawTransaction 列表批量 insert。

    返回 (created_count, skipped_count_due_to_dup_unique_key)。
    spec § 5.1 step 4 + § 6.1 ①(同源跳过)。

    本函数只**插入数据**,不做跨源去重(Task 10-13)和分类(Task 14)。
    """
    source_short = _short_source(source_type)

    # 拉一次该 user 已存在的 source_unique_key 集合,避免 N+1 查询
    seen: set[str] = set(
        row[0] for row in db.execute(
            select(Transaction.source_unique_key).where(
                Transaction.user_id == user_id,
                Transaction.source_unique_key.isnot(None),
            )
        ).all() if row[0] is not None
    )

    created = 0
    skipped = 0
    for idx, raw in enumerate(raw_transactions):
        if raw.external_tx_id:
            unique_key = f"{source_short}:{raw.external_tx_id}"
        else:
            unique_key = _synth_unique_key(
                source_short, statement_import_id, idx,
                raw.merchant_raw or "", raw.amount, raw.tx_time,
            )
        if unique_key in seen:
            skipped += 1
            continue
        seen.add(unique_key)

        merchant_norm = normalize_merchant(raw.merchant_raw)
        tx = Transaction(
            user_id=user_id,
            account_id=account_id,
            statement_import_id=statement_import_id,
            tx_kind=raw.tx_kind,
            tx_time=raw.tx_time,
            post_time=raw.post_time,
            amount=raw.amount,
            currency=raw.currency,
            amount_settled_cny=raw.amount_settled_cny,
            merchant_raw=raw.merchant_raw or None,
            merchant_normalized=merchant_norm or None,
            counterparty_raw=raw.counterparty_raw,
            description_raw=raw.description_raw,
            category_id=None,
            classification_confidence=None,
            source=source_short,
            external_tx_id=raw.external_tx_id,
            external_merchant_id=raw.external_merchant_id,
            payment_method_raw=raw.payment_method_raw,
            is_mirror=False,
            mirror_of_id=None,
            source_unique_key=unique_key,
            raw_payload=raw.raw_row,
        )
        db.add(tx)
        created += 1

    db.flush()
    return created, skipped


# ---------------------------------------------------------------------------
# Task 15: run_import_pipeline(总编排)
# ---------------------------------------------------------------------------

def _infer_source_type_from_parser(pr: ParseResult) -> str:
    """从 ParseResult.account_hint 派生 statement_imports.source_type。"""
    t = pr.account_hint.type
    inst = pr.account_hint.institution
    if t == "alipay":
        return "alipay_csv"
    if t == "wechat":
        return "wechat_xlsx"
    if t == "bank_debit" and "交通" in (inst or ""):
        return "bank_pdf_bocom_debit"
    if t == "bank_credit" and "建设" in (inst or ""):
        return "bank_pdf_ccb_credit"
    raise ValueError(f"cannot infer source_type from account_hint={pr.account_hint!r}")


def _persist_and_return_ids(
    db: Session,
    *,
    user_id: int,
    account_id: int,
    statement_import_id: int,
    source_type: str,
    raw_transactions: list[RawTransaction],
) -> list[int]:
    """persist_raw_transactions 包装,返回新创建的 tx ids 列表。

    现有 persist_raw_transactions 返回 (created, skipped),不返回 ids。本函数复用其逻辑
    但在 add 后收集 id(flush 后 id 即可见)。为保持向后兼容不改原函数签名。
    """
    source_short = _short_source(source_type)
    seen: set[str] = set(
        row[0] for row in db.execute(
            select(Transaction.source_unique_key).where(
                Transaction.user_id == user_id,
                Transaction.source_unique_key.isnot(None),
            )
        ).all() if row[0] is not None
    )
    new_ids: list[int] = []
    for idx, raw in enumerate(raw_transactions):
        if raw.external_tx_id:
            unique_key = f"{source_short}:{raw.external_tx_id}"
        else:
            unique_key = _synth_unique_key(
                source_short, statement_import_id, idx,
                raw.merchant_raw or "", raw.amount, raw.tx_time,
            )
        if unique_key in seen:
            continue
        seen.add(unique_key)
        merchant_norm = normalize_merchant(raw.merchant_raw)
        tx = Transaction(
            user_id=user_id, account_id=account_id,
            statement_import_id=statement_import_id,
            tx_kind=raw.tx_kind, tx_time=raw.tx_time, post_time=raw.post_time,
            amount=raw.amount, currency=raw.currency,
            amount_settled_cny=raw.amount_settled_cny,
            merchant_raw=raw.merchant_raw or None,
            merchant_normalized=merchant_norm or None,
            counterparty_raw=raw.counterparty_raw, description_raw=raw.description_raw,
            category_id=None, classification_confidence=None,
            source=source_short, external_tx_id=raw.external_tx_id,
            external_merchant_id=raw.external_merchant_id,
            payment_method_raw=raw.payment_method_raw,
            is_mirror=False, mirror_of_id=None,
            source_unique_key=unique_key, raw_payload=raw.raw_row,
        )
        db.add(tx)
        db.flush()  # 立即 flush 拿 id
        new_ids.append(tx.id)
    return new_ids


def run_import_pipeline(
    db: Session,
    *,
    user_id: int,
    file_bytes: bytes,
    filename: str,
) -> ImportResponse:
    """spec § 5.1 全流程编排:parser → file_hash → account → si → persist → dedup → classify。

    - UnsupportedStatementError 透传(HTTP 层转 400)
    - DuplicateImportError 透传(HTTP 层转 409)
    """
    pr = route_and_parse(file_bytes, filename)
    fh = file_sha256(file_bytes)
    account = ensure_account_for_hint(db, user_id, pr.account_hint)
    source_type = _infer_source_type_from_parser(pr)
    si = ensure_statement_import(
        db, user_id=user_id, account_id=account.id,
        source_type=source_type, filename=filename, file_hash=fh, parse_result=pr,
    )
    created_ids = _persist_and_return_ids(
        db, user_id=user_id, account_id=account.id,
        statement_import_id=si.id, source_type=source_type,
        raw_transactions=pr.raw_transactions,
    )
    pairs = run_dedup_pass(db, user_id=user_id, new_tx_ids=created_ids)
    strong_confirmed = sum(1 for p in pairs if p.match_kind == "strong" and p.status == "confirmed")
    pending = sum(1 for p in pairs if p.status == "pending")
    classified, marker_only = classify_batch(db, user_id=user_id, tx_ids=created_ids)
    si.raw_row_count = pr.metadata.get("raw_row_count", len(pr.raw_transactions))
    si.imported_count = len(created_ids)
    si.deduped_count = strong_confirmed
    si.classified_count = classified
    db.flush()
    return ImportResponse(
        import_id=si.id,
        source_type=source_type,
        raw_row_count=si.raw_row_count,
        imported_count=len(created_ids),
        deduped_strong_count=strong_confirmed,
        dedup_pending_count=pending,
        classified_count=classified,
        unclassified_count=len(created_ids) - classified - marker_only,
    )
