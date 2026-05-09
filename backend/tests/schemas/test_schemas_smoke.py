"""schemas 包导入 + 关键字段烟测。"""
from datetime import datetime
from decimal import Decimal


def test_re_export_intact():
    from app import schemas
    expected = {
        "LoginIn", "LoginOut", "MeOut",
        "AccountCreate", "AccountOut", "AccountUpdate",
        "CategoryCreate", "CategoryOut", "CategoryUpdate",
        "MerchantRuleCreate", "MerchantRuleOut", "MerchantRuleUpdate",
        "StatementImportOut", "StatementImportListOut", "ImportResponse", "ReviewBundle",
        "TransactionOut", "TransactionListOut", "TransactionPatchIn",
        "TransactionQuery", "BulkUpdateByMerchantIn", "BulkUpdateResult",
        "DedupPairOut", "PendingPairListOut", "DedupDecisionIn",
        "SummaryOut", "SummaryBreakdownItem",
    }
    assert expected.issubset(set(dir(schemas)))


def test_login_in_validates():
    from app.schemas import LoginIn
    LoginIn(username="admin", password="x")
    import pytest
    with pytest.raises(ValueError):
        LoginIn(username="", password="x")


def test_transaction_query_defaults():
    from app.schemas import TransactionQuery
    q = TransactionQuery()
    assert q.limit == 50
    assert q.offset == 0


def test_transaction_query_validates_limit():
    from app.schemas import TransactionQuery
    import pytest
    with pytest.raises(ValueError):
        TransactionQuery(limit=0)
    with pytest.raises(ValueError):
        TransactionQuery(limit=1000)


def test_review_bundle_model_rebuild_ok():
    """forward ref 在 Step 6.7 末尾 model_rebuild — 实例化不抛错即说明 OK。"""
    from app.schemas import ReviewBundle, StatementImportOut
    rb = ReviewBundle(
        statement=StatementImportOut(
            id=1, account_id=None, source_type="alipay_csv",
            filename="x.csv", file_hash="h", period_start=None, period_end=None,
            raw_row_count=0, imported_count=0, deduped_count=0, classified_count=0,
            imported_at=datetime(2026, 5, 9),
        ),
        pending_pairs=[], unclassified_transactions=[],
    )
    assert rb.statement.id == 1
