"""Dedup API — spec § 6 + § 9.1。"""
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, DbDep
from app.models import DedupCandidate, Transaction
from app.schemas import DedupDecisionIn, DedupPairOut, PendingPairListOut


router = APIRouter(prefix="/dedup", tags=["dedup"])


@router.get("/pending", response_model=PendingPairListOut)
def list_pending(
    user: CurrentUserDep, db: DbDep,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PendingPairListOut:
    where = (DedupCandidate.user_id == user.id) & (DedupCandidate.status == "pending")
    total = db.execute(select(func.count()).select_from(DedupCandidate).where(where)).scalar_one()
    items = db.execute(
        select(DedupCandidate).where(where)
        .order_by(DedupCandidate.id.asc()).limit(limit).offset(offset)
    ).scalars().all()
    return PendingPairListOut(
        items=[DedupPairOut.model_validate(p) for p in items], total=total,
    )


def _decide(db, user_id: int, pair_id: int, action: str) -> DedupCandidate:
    pair = db.execute(
        select(DedupCandidate).where(
            DedupCandidate.id == pair_id, DedupCandidate.user_id == user_id,
        )
    ).scalar_one_or_none()
    if pair is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dedup_pair not found")
    if pair.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT,
            f"pair already {pair.status}")
    if action == "confirm":
        mirror = db.execute(
            select(Transaction).where(
                Transaction.id == pair.mirror_tx_id,
                Transaction.user_id == user_id,
            )
        ).scalar_one()
        mirror.is_mirror = True
        mirror.mirror_of_id = pair.primary_tx_id
        pair.status = "confirmed"
    elif action == "reject":
        # 也要清掉 mirror 已被错误标的(② 多匹配场景下,可能两边都在 pending pair)
        mirror = db.execute(
            select(Transaction).where(
                Transaction.id == pair.mirror_tx_id,
                Transaction.user_id == user_id,
            )
        ).scalar_one()
        if mirror.mirror_of_id == pair.primary_tx_id:
            mirror.is_mirror = False
            mirror.mirror_of_id = None
        pair.status = "rejected"
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
            f"unknown action: {action!r}")
    pair.decided_at = datetime.now(UTC)
    db.flush()
    return pair


@router.post("/{pair_id}/confirm", response_model=DedupPairOut)
def confirm_pair(
    pair_id: int, body: DedupDecisionIn, user: CurrentUserDep, db: DbDep,
) -> DedupPairOut:
    pair = _decide(db, user.id, pair_id, body.action)
    return DedupPairOut.model_validate(pair)


@router.post("/{pair_id}/reject", response_model=DedupPairOut)
def reject_pair(
    pair_id: int, user: CurrentUserDep, db: DbDep,
) -> DedupPairOut:
    """语法糖等价于 /confirm body={'action': 'reject'}。"""
    pair = _decide(db, user.id, pair_id, "reject")
    return DedupPairOut.model_validate(pair)
