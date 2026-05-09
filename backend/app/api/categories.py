"""Categories API — spec § 9.1 + § 4.1。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.models import Category
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate
from pydantic import BaseModel


class CategoryListOut(BaseModel):
    items: list[CategoryOut]
    total: int


router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=CategoryListOut)
def list_categories(user: CurrentUserDep, db: DbDep) -> CategoryListOut:
    items = db.execute(
        select(Category).where(Category.user_id == user.id)
        .order_by(Category.sort_order.asc(), Category.id.asc())
    ).scalars().all()
    return CategoryListOut(
        items=[CategoryOut.model_validate(c) for c in items], total=len(items),
    )


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(
    body: CategoryCreate, user: CurrentUserDep, db: DbDep,
) -> CategoryOut:
    if body.parent_id is not None:
        parent = db.execute(
            select(Category).where(
                Category.id == body.parent_id, Category.user_id == user.id,
            )
        ).scalar_one_or_none()
        if parent is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "parent category not found")
    cat = Category(
        user_id=user.id, name=body.name, kind=body.kind, parent_id=body.parent_id,
        icon=body.icon, color=body.color, sort_order=body.sort_order,
    )
    db.add(cat); db.flush()
    return CategoryOut.model_validate(cat)


def _get_cat_or_404(db, user_id: int, cat_id: int) -> Category:
    cat = db.execute(
        select(Category).where(Category.id == cat_id, Category.user_id == user_id)
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    return cat


@router.patch("/{cat_id}", response_model=CategoryOut)
def update_category(
    cat_id: int, body: CategoryUpdate, user: CurrentUserDep, db: DbDep,
) -> CategoryOut:
    cat = _get_cat_or_404(db, user.id, cat_id)
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(cat, field, val)
    db.flush()
    return CategoryOut.model_validate(cat)


@router.delete("/{cat_id}", status_code=204)
def delete_category(cat_id: int, user: CurrentUserDep, db: DbDep) -> None:
    cat = _get_cat_or_404(db, user.id, cat_id)
    # 先检查是否有子分类(防止意外删除)
    has_children = db.execute(
        select(Category.id).where(
            Category.user_id == user.id, Category.parent_id == cat_id
        ).limit(1)
    ).first()
    if has_children:
        raise HTTPException(status.HTTP_409_CONFLICT,
            "category has children; remove or reparent them first")
    db.delete(cat); db.flush()
    return None
