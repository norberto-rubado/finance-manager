"""导入流水线编排 service — spec § 5.1。

本切片任务拆分:
- Task 8(本 task):file_sha256 / ensure_account_for_hint / ensure_statement_import
- Task 9:persist_raw_transactions
- Task 15:run_import_pipeline(总编排:parser → setup → persist → dedup → classify)
"""
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, StatementImport
from app.services.statement_parser import AccountHint, ParseResult


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
