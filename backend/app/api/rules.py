"""MerchantRules API — spec § 9.1 + § 7。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.models import Category, MerchantRule
from app.schemas import MerchantRuleCreate, MerchantRuleOut, MerchantRuleUpdate
from pydantic import BaseModel


class RuleListOut(BaseModel):
    items: list[MerchantRuleOut]
    total: int


router = APIRouter(prefix="/rules", tags=["rules"])


def _validate_category_or_marker(db, user_id: int, category_id: int | None) -> None:
    if category_id is None:
        return  # marker rule(spec § 7.1)
    cat = db.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")


@router.get("", response_model=RuleListOut)
def list_rules(user: CurrentUserDep, db: DbDep) -> RuleListOut:
    items = db.execute(
        select(MerchantRule).where(MerchantRule.user_id == user.id)
        .order_by(MerchantRule.priority.asc(), MerchantRule.id.asc())
    ).scalars().all()
    return RuleListOut(
        items=[MerchantRuleOut.model_validate(r) for r in items], total=len(items),
    )


@router.post("", response_model=MerchantRuleOut, status_code=201)
def create_rule(
    body: MerchantRuleCreate, user: CurrentUserDep, db: DbDep,
) -> MerchantRuleOut:
    _validate_category_or_marker(db, user.id, body.category_id)
    rule = MerchantRule(
        user_id=user.id, pattern=body.pattern, match_kind=body.match_kind,
        category_id=body.category_id, priority=body.priority,
    )
    db.add(rule); db.flush()
    return MerchantRuleOut.model_validate(rule)


def _get_rule_or_404(db, user_id: int, rule_id: int) -> MerchantRule:
    r = db.execute(
        select(MerchantRule).where(
            MerchantRule.id == rule_id, MerchantRule.user_id == user_id,
        )
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    return r


@router.patch("/{rule_id}", response_model=MerchantRuleOut)
def update_rule(
    rule_id: int, body: MerchantRuleUpdate, user: CurrentUserDep, db: DbDep,
) -> MerchantRuleOut:
    rule = _get_rule_or_404(db, user.id, rule_id)
    data = body.model_dump(exclude_unset=True)
    if "category_id" in data:
        _validate_category_or_marker(db, user.id, data["category_id"])
    for field, val in data.items():
        setattr(rule, field, val)
    db.flush()
    return MerchantRuleOut.model_validate(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, user: CurrentUserDep, db: DbDep) -> None:
    rule = _get_rule_or_404(db, user.id, rule_id)
    db.delete(rule); db.flush()
    return None
