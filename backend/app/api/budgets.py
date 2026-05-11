"""Budgets API — spec § 4.4。"""
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUserDep, DbDep
from app.models import Budget
from app.schemas import BudgetCopyIn, BudgetIn, BudgetOut
from app.services.budget import (
    copy_budgets_from,
    list_budgets,
    upsert_budget,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=list[BudgetOut])
def list_endpoint(
    user: CurrentUserDep, db: DbDep,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
) -> list[Budget]:
    return list_budgets(db, user_id=user.id, period_year=year, period_month=month)


@router.put("", response_model=BudgetOut)
def upsert_endpoint(
    user: CurrentUserDep, db: DbDep,
    body: BudgetIn,
) -> Budget:
    return upsert_budget(
        db,
        user_id=user.id,
        period_year=body.period_year,
        period_month=body.period_month,
        category_id=body.category_id,
        amount=body.amount,
        note=body.note,
    )
