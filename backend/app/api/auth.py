"""认证端点 — spec § 10.1。"""
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import (
    SESSION_COOKIE_NAME,
    CurrentUserDep,
    DbDep,
)
from app.core.config import get_settings
from app.models import User
from app.schemas import LoginIn, LoginOut, MeOut
from app.services.auth import create_access_token, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


_TOKEN_EXPIRES_MINUTES = 60 * 24 * 30  # 30 天,与 cookie 同寿


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, response: Response, db: DbDep) -> LoginOut:
    user = db.execute(select(User).where(User.username == body.username)).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        # 用户名不存在 vs 密码错 — 返回同样的 401,避免 user enum
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    token = create_access_token(subject=user.username, expires_minutes=_TOKEN_EXPIRES_MINUTES)
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        # 本机开发 http,Secure=False;生产 Caddy https 时改为 True(留 V2 配置化)
        secure=False,
        max_age=_TOKEN_EXPIRES_MINUTES * 60,
        path="/",
    )
    return LoginOut(user_id=user.id, username=user.username)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return None


@router.get("/me", response_model=MeOut)
def me(user: CurrentUserDep) -> MeOut:
    return MeOut.model_validate(user)
