"""Dedup schemas — spec § 6 + § 8.1。"""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


MatchKind = Literal["strong", "bridge", "conversation"]
PairStatus = Literal["pending", "confirmed", "rejected"]


class DedupPairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    primary_tx_id: int
    mirror_tx_id: int
    match_kind: MatchKind
    confidence: float
    status: PairStatus
    reasoning: dict[str, Any] | None


class PendingPairListOut(BaseModel):
    items: list[DedupPairOut]
    total: int


class DedupDecisionIn(BaseModel):
    """POST /api/dedup/{pair_id}/confirm | /reject body."""
    action: Literal["confirm", "reject"]
    note: str | None = Field(None, max_length=512)
