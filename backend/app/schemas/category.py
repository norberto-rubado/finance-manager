"""Category schemas — spec § 4.1 树形分类。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


CategoryKind = Literal["expense", "income", "neutral"]


class CategoryCreate(BaseModel):
    name: str = Field(..., max_length=64)
    parent_id: int | None = None
    kind: CategoryKind
    icon: str | None = None
    color: str | None = None
    sort_order: int = 100


class CategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    icon: str | None = None
    color: str | None = None
    sort_order: int | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    parent_id: int | None
    kind: CategoryKind
    icon: str | None
    color: str | None
    sort_order: int
