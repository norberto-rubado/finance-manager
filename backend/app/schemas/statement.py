"""StatementImport / Review schemas — spec § 5.1 + § 9.1 复查页。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class StatementImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int | None
    source_type: str
    filename: str
    file_hash: str
    period_start: datetime | None
    period_end: datetime | None
    raw_row_count: int
    imported_count: int
    deduped_count: int
    classified_count: int
    imported_at: datetime


class StatementImportListOut(BaseModel):
    items: list[StatementImportOut]
    total: int


class ImportResponse(BaseModel):
    """POST /api/statements/import 响应。"""
    import_id: int
    source_type: str
    raw_row_count: int
    imported_count: int
    deduped_strong_count: int      # 自动去重(② + ③)
    dedup_pending_count: int       # 待审核(④ + ⑤)
    classified_count: int
    unclassified_count: int


class ReviewBundle(BaseModel):
    """GET /api/statements/{id}/review。"""
    statement: StatementImportOut
    pending_pairs: list["DedupPairOut"]              # forward ref
    unclassified_transactions: list["TransactionOut"] # forward ref


# 解 forward refs
from app.schemas.dedup import DedupPairOut          # noqa: E402
from app.schemas.transaction import TransactionOut  # noqa: E402
ReviewBundle.model_rebuild()
