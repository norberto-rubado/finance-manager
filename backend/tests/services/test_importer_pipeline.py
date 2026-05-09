"""run_import_pipeline 集成测试 — 用真实样本走全流程。"""
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import StatementImport, Transaction, User
from app.services.importer import DuplicateImportError, run_import_pipeline
from app.services.statement_parser import UnsupportedStatementError


_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "statements"


@pytest.fixture
def test_user(db) -> User:
    u = User(username="ip", password_hash="$2b$12$" + "x" * 53)
    db.add(u)
    db.flush()
    return u


def _load(name: str) -> bytes:
    p = _FIXTURES / name
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    return p.read_bytes()


def test_pipeline_alipay_full_run(db, test_user):
    bytes_ = _load("alipay_sample.csv")
    resp = run_import_pipeline(
        db, user_id=test_user.id, file_bytes=bytes_,
        filename="alipay_sample.csv",
    )
    db.flush()
    assert resp.import_id is not None
    assert resp.source_type == "alipay_csv"
    assert resp.imported_count >= 1
    txs = db.execute(select(Transaction).where(
        Transaction.user_id == test_user.id, Transaction.source == "alipay")
    ).scalars().all()
    assert len(txs) == resp.imported_count


def test_pipeline_duplicate_file_raises(db, test_user):
    bytes_ = _load("alipay_sample.csv")
    run_import_pipeline(db, user_id=test_user.id, file_bytes=bytes_,
        filename="alipay_sample.csv")
    db.flush()
    with pytest.raises(DuplicateImportError):
        run_import_pipeline(db, user_id=test_user.id, file_bytes=bytes_,
            filename="alipay_sample_v2.csv")  # 不同文件名,但 hash 相同


def test_pipeline_unsupported_file_raises(db, test_user):
    with pytest.raises(UnsupportedStatementError):
        run_import_pipeline(db, user_id=test_user.id,
            file_bytes=b"random text not any statement", filename="x.txt")


def test_pipeline_count_consistency(db, test_user):
    """imported_count + classified + unclassified + marker_only 关系自洽。"""
    bytes_ = _load("alipay_sample.csv")
    resp = run_import_pipeline(db, user_id=test_user.id, file_bytes=bytes_,
        filename="alipay_sample.csv")
    # classified + unclassified + marker_only = imported_count
    # marker_only = imported - classified - unclassified
    assert (resp.classified_count + resp.unclassified_count) <= resp.imported_count
    assert resp.unclassified_count >= 0
