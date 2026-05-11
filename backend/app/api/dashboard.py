"""Dashboard API — spec § 4.4。"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, DbDep
from app.schemas import DashboardSnapshot
from app.services.dashboard import compute_dashboard_snapshot

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/snapshot", response_model=DashboardSnapshot)
def snapshot_endpoint(
    user: CurrentUserDep,
    db: DbDep,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
    client_date: Annotated[
        date,
        Query(description="前端本地时区 YYYY-MM-DD,后端用它算 day_of_month / is_current_month"),
    ],
) -> dict:
    return compute_dashboard_snapshot(
        db, user_id=user.id, query_year=year, query_month=month,
        client_date=client_date,
    )
