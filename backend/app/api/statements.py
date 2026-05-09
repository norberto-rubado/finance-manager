"""Statements API — spec § 9.1 + § 5.1。

本 task(15):POST /import
Task 16:list / detail / review
"""
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.models import DedupCandidate, StatementImport, Transaction
from app.schemas import (
    ImportResponse,
    ReviewBundle,
    StatementImportListOut,
    StatementImportOut,
    TransactionOut,
)
from app.schemas.dedup import DedupPairOut
from app.services.importer import DuplicateImportError, run_import_pipeline
from app.services.statement_parser import UnsupportedStatementError


router = APIRouter(prefix="/statements", tags=["statements"])


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/import", response_model=ImportResponse)
async def import_statement(
    user: CurrentUserDep, db: DbDep, file: UploadFile = File(...),
) -> ImportResponse:
    """multipart upload → 跑导入流水线。spec § 5.1。"""
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"file > {_MAX_UPLOAD_BYTES // 1024 // 1024}MB")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")
    try:
        return run_import_pipeline(
            db, user_id=user.id, file_bytes=raw,
            filename=file.filename or "unknown",
        )
    except UnsupportedStatementError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
            f"unsupported statement: {e}") from e
    except DuplicateImportError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ValueError as e:
        # 解析器内部错(如 GBK decode 失败 / 表头缺列)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.get("", response_model=StatementImportListOut)
def list_statements(
    user: CurrentUserDep, db: DbDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> StatementImportListOut:
    base = select(StatementImport).where(StatementImport.user_id == user.id)
    total = db.execute(
        select(StatementImport.id).where(StatementImport.user_id == user.id)
    ).all()
    items = db.execute(
        base.order_by(StatementImport.imported_at.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    return StatementImportListOut(
        items=[StatementImportOut.model_validate(s) for s in items],
        total=len(total),
    )


@router.get("/{import_id}", response_model=StatementImportOut)
def get_statement(
    import_id: int, user: CurrentUserDep, db: DbDep,
) -> StatementImportOut:
    si = db.execute(
        select(StatementImport).where(
            StatementImport.id == import_id,
            StatementImport.user_id == user.id,
        )
    ).scalar_one_or_none()
    if si is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "statement_import not found")
    return StatementImportOut.model_validate(si)


@router.get("/{import_id}/review", response_model=ReviewBundle)
def get_review_bundle(
    import_id: int, user: CurrentUserDep, db: DbDep,
) -> ReviewBundle:
    """spec § 9.1 复查页数据:本批次 pending pairs + 未分类交易。"""
    si = db.execute(
        select(StatementImport).where(
            StatementImport.id == import_id,
            StatementImport.user_id == user.id,
        )
    ).scalar_one_or_none()
    if si is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "statement_import not found")

    # 本批次的 transaction ids
    tx_rows = db.execute(
        select(Transaction.id).where(
            Transaction.user_id == user.id,
            Transaction.statement_import_id == import_id,
        )
    ).all()
    tx_ids = [r[0] for r in tx_rows]

    # 未分类交易(category_id IS NULL)
    unclassified = db.execute(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.statement_import_id == import_id,
            Transaction.category_id.is_(None),
        ).order_by(Transaction.tx_time.desc())
    ).scalars().all()

    # 涉及本批次 tx 的 pending pair(primary 或 mirror 在本批次内)
    pending_pairs: list[DedupCandidate] = []
    if tx_ids:
        pending_pairs = list(db.execute(
            select(DedupCandidate).where(
                DedupCandidate.user_id == user.id,
                DedupCandidate.status == "pending",
                (DedupCandidate.primary_tx_id.in_(tx_ids))
                | (DedupCandidate.mirror_tx_id.in_(tx_ids)),
            ).order_by(DedupCandidate.id.asc())
        ).scalars().all())

    return ReviewBundle(
        statement=StatementImportOut.model_validate(si),
        pending_pairs=[DedupPairOut.model_validate(p) for p in pending_pairs],
        unclassified_transactions=[TransactionOut.model_validate(t) for t in unclassified],
    )
