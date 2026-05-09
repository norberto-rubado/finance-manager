"""FastAPI 依赖:DbDep(复用 core.db.get_db) / current_user。

current_user 从 cookie `fm_session` 解 JWT,失败返回 401。
spec § 10.1。
"""
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db  # 复用 slice A 已定义的 session 工厂
from app.models import User
from app.services.auth import InvalidTokenError, decode_access_token


SESSION_COOKIE_NAME = "fm_session"

DbDep = Annotated[Session, Depends(get_db)]


def current_user(
    db: DbDep,
    fm_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User:
    """从 cookie 取 JWT 解出 user。失败 401。"""
    if not fm_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing session cookie")
    try:
        payload = decode_access_token(fm_session)
    except InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e
    username = payload.get("sub")
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub")
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user


CurrentUserDep = Annotated[User, Depends(current_user)]
