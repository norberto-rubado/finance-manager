"""MerchantRule schemas — spec § 4.1 + § 7。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


MatchKind = Literal["exact", "contains", "regex", "fuzzy"]


class MerchantRuleCreate(BaseModel):
    pattern: str = Field(..., max_length=255)
    match_kind: MatchKind
    category_id: int | None = None  # None = marker rule(spec § 7.1)
    priority: int = 100


class MerchantRuleUpdate(BaseModel):
    pattern: str | None = None
    match_kind: MatchKind | None = None
    category_id: int | None = None
    priority: int | None = None


class MerchantRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pattern: str
    match_kind: MatchKind
    category_id: int | None
    priority: int
    hit_count: int
