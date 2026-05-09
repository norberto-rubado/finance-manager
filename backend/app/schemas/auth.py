"""认证 schemas。spec § 10.1。"""
from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class LoginOut(BaseModel):
    """登录成功响应(token 在 cookie,body 只回 user 信息)。"""
    user_id: int
    username: str


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
