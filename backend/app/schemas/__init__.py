"""HTTP 边界 Pydantic schema 集中 re-export。

约定:
- XxxIn:request body
- XxxOut:response body(from_attributes=True,可从 ORM 对象直接构造)
- XxxQuery:query string(FastAPI Query 用)
"""
from app.schemas.account import AccountBalanceOut, AccountCreate, AccountOut, AccountUpdate
from app.schemas.api_token import (
    ApiTokenCreate,
    ApiTokenCreateResp,
    ApiTokenListOut,
    ApiTokenOut,
    ApiTokenVerifyOut,
)
from app.schemas.auth import LoginIn, LoginOut, MeOut
from app.schemas.budget import BudgetCopyIn, BudgetIn, BudgetOut
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.dashboard import (
    DashboardSnapshot,
    SnapshotCategory,
    SnapshotPace,
    SnapshotPending,
    SnapshotPeriod,
    SnapshotTotal,
    SnapshotTrendPoint,
)
from app.schemas.dedup import DedupDecisionIn, DedupPairOut, PendingPairListOut
from app.schemas.rule import MerchantRuleCreate, MerchantRuleOut, MerchantRuleUpdate
from app.schemas.statement import (
    ImportResponse,
    ReviewBundle,
    StatementImportListOut,
    StatementImportOut,
)
from app.schemas.summary import SummaryBreakdownItem, SummaryOut
from app.schemas.transaction import (
    BulkUpdateByMerchantIn,
    BulkUpdateResult,
    MerchantSearchOut,
    MerchantStatItem,
    TransactionCreateIn,
    TransactionListOut,
    TransactionOut,
    TransactionPatchIn,
    TransactionQuery,
)

__all__ = [
    "LoginIn", "LoginOut", "MeOut",
    "AccountCreate", "AccountOut", "AccountUpdate", "AccountBalanceOut",
    "BudgetIn", "BudgetOut", "BudgetCopyIn",
    "CategoryCreate", "CategoryOut", "CategoryUpdate",
    "MerchantRuleCreate", "MerchantRuleOut", "MerchantRuleUpdate",
    "StatementImportOut", "StatementImportListOut", "ImportResponse", "ReviewBundle",
    "TransactionCreateIn", "TransactionOut", "TransactionListOut", "TransactionPatchIn",
    "TransactionQuery", "BulkUpdateByMerchantIn", "BulkUpdateResult",
    "MerchantSearchOut", "MerchantStatItem",
    "DedupPairOut", "PendingPairListOut", "DedupDecisionIn",
    "SummaryOut", "SummaryBreakdownItem",
    "DashboardSnapshot", "SnapshotPeriod", "SnapshotTotal", "SnapshotPace",
    "SnapshotCategory", "SnapshotTrendPoint", "SnapshotPending",
    "ApiTokenCreate", "ApiTokenCreateResp", "ApiTokenListOut",
    "ApiTokenOut", "ApiTokenVerifyOut",
]
