"""Accounts API — spec § 9.1 + § 4.1。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.models import Account
from app.schemas import AccountCreate, AccountOut, AccountUpdate
from pydantic import BaseModel


class AccountListOut(BaseModel):
    items: list[AccountOut]
    total: int


router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=AccountListOut)
def list_accounts(user: CurrentUserDep, db: DbDep) -> AccountListOut:
    items = db.execute(
        select(Account).where(Account.user_id == user.id)
        .order_by(Account.id.asc())
    ).scalars().all()
    return AccountListOut(
        items=[AccountOut.model_validate(a) for a in items], total=len(items),
    )


@router.post("", response_model=AccountOut, status_code=201)
def create_account(
    body: AccountCreate, user: CurrentUserDep, db: DbDep,
) -> AccountOut:
    acc = Account(
        user_id=user.id, name=body.name, type=body.type,
        institution=body.institution, last4=body.last4, currency=body.currency,
    )
    db.add(acc); db.flush()
    return AccountOut.model_validate(acc)


def _get_acc_or_404(db, user_id: int, acc_id: int) -> Account:
    acc = db.execute(
        select(Account).where(Account.id == acc_id, Account.user_id == user_id)
    ).scalar_one_or_none()
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    return acc


@router.patch("/{acc_id}", response_model=AccountOut)
def update_account(
    acc_id: int, body: AccountUpdate, user: CurrentUserDep, db: DbDep,
) -> AccountOut:
    acc = _get_acc_or_404(db, user.id, acc_id)
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(acc, field, val)
    db.flush()
    return AccountOut.model_validate(acc)


@router.delete("/{acc_id}", status_code=204)
def delete_account(acc_id: int, user: CurrentUserDep, db: DbDep) -> None:
    """有 transactions 引用时拒绝删,推荐 archived=True。"""
    acc = _get_acc_or_404(db, user.id, acc_id)
    from app.models import Transaction
    has_tx = db.execute(
        select(Transaction.id).where(Transaction.account_id == acc_id).limit(1)
    ).first()
    if has_tx:
        raise HTTPException(status.HTTP_409_CONFLICT,
            "account has transactions; archive instead of delete")
    db.delete(acc); db.flush()
    return None
