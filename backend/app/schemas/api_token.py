"""API token schemas — spec § 10.2。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ApiTokenCreate(BaseModel):
    """POST /api/admin/tokens body。"""
    name: str = Field(..., min_length=1, max_length=128)
    scopes: str = Field("read,write", max_length=64)


class ApiTokenOut(BaseModel):
    """list / 单条返回(不含 plain / hash)。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    scopes: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiTokenCreateResp(BaseModel):
    """POST /api/admin/tokens 返回:plain 仅这一次,token 元信息按 ApiTokenOut。"""
    plain_token: str           # 用户必须立即保存,无后悔药
    token: ApiTokenOut


class ApiTokenListOut(BaseModel):
    items: list[ApiTokenOut]
    total: int


class ApiTokenVerifyOut(BaseModel):
    """POST /api/admin/tokens/verify — MCP server 内部端点用。"""
    user_id: int
    username: str
    scopes: str
