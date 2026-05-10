"""Admin tokens API — spec § 10.2。

POST   /api/admin/tokens          — 创建,返回 plain(仅一次)
GET    /api/admin/tokens          — list(不含 plain / hash)
DELETE /api/admin/tokens/{id}     — 吊销(soft delete via revoked_at)
POST   /api/admin/tokens/verify   — 给 MCP server 内部用,Bearer 验证返回 user 信息
"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import BearerUserDep, CurrentUserDep, DbDep
from app.models import ApiToken
from app.schemas import (
    ApiTokenCreate,
    ApiTokenCreateResp,
    ApiTokenListOut,
    ApiTokenOut,
    ApiTokenVerifyOut,
)
from app.services.api_token import (
    create_api_token, list_tokens, revoke_token,
)


router = APIRouter(prefix="/admin/tokens", tags=["admin-tokens"])


@router.post("", response_model=ApiTokenCreateResp, status_code=status.HTTP_201_CREATED)
def create(
    body: ApiTokenCreate, user: CurrentUserDep, db: DbDep,
) -> ApiTokenCreateResp:
    plain, token = create_api_token(
        db, user_id=user.id, name=body.name, scopes=body.scopes,
    )
    return ApiTokenCreateResp(
        plain_token=plain,
        token=ApiTokenOut.model_validate(token),
    )


@router.get("", response_model=ApiTokenListOut)
def list_(
    user: CurrentUserDep, db: DbDep,
) -> ApiTokenListOut:
    rows = list_tokens(db, user_id=user.id)
    return ApiTokenListOut(
        items=[ApiTokenOut.model_validate(t) for t in rows], total=len(rows),
    )


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke(
    token_id: int, user: CurrentUserDep, db: DbDep,
) -> None:
    ok = revoke_token(db, token_id=token_id, user_id=user.id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "token not found")
    return None


@router.post("/verify", response_model=ApiTokenVerifyOut)
def verify(
    user: BearerUserDep, db: DbDep,
) -> ApiTokenVerifyOut:
    """MCP server 启动时调一次确认 token 合法,后续每次工具调用也可调以拿 user info。

    复用 BearerUserDep — 内部已查表 + 更新 last_used_at + 验未吊销。
    取最近 last_used_at 的未吊销 token(就是刚 verify 那条)拿 scopes。
    """
    recent = db.execute(
        select(ApiToken).where(
            ApiToken.user_id == user.id,
            ApiToken.revoked_at.is_(None),
        ).order_by(ApiToken.last_used_at.desc().nulls_last()).limit(1)
    ).scalar_one()
    return ApiTokenVerifyOut(
        user_id=user.id,
        username=user.username,
        scopes=recent.scopes,
    )
