"""Summary API — spec § 8.1 + § 9.1 首页本月概览。"""
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUserDep, DbDep
from app.schemas import SummaryBreakdownItem, SummaryOut
from app.schemas.summary import GroupBy, Period
from app.services.summary import compute_summary


router = APIRouter(prefix="/summary", tags=["summary"])


def _period_range(period: Period, now: datetime) -> tuple[datetime, datetime]:
    """计算 period 的默认 (date_from, date_to)。"""
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if period == "week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7)
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    if period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
        return start, end
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown period: {period!r}")


@router.get("", response_model=SummaryOut)
def get_summary(
    user: CurrentUserDep, db: DbDep,
    period: Period = Query("month"),
    group_by: GroupBy = Query("category"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
) -> SummaryOut:
    now = datetime.now(UTC).replace(tzinfo=None)
    df, dt = _period_range(period, now)
    if date_from is not None:
        df = date_from
    if date_to is not None:
        dt = date_to

    data = compute_summary(db, user_id=user.id, date_from=df, date_to=dt,
        group_by=group_by)
    return SummaryOut(
        period=period, date_from=df, date_to=dt, group_by=group_by,
        total_expense=data["total_expense"],
        total_income=data["total_income"],
        breakdown=[SummaryBreakdownItem(**item) for item in data["breakdown"]],
    )
