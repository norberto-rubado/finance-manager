"""FastAPI 依赖:DbDep / current_user(cookie 或 Bearer 双通道)。

current_user 优先 cookie+JWT(spec § 10.1);若 cookie 缺,fallback 到
Authorization: Bearer <api_token>(spec § 10.2)。两种都失败返 401。
"""
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import User
from app.services.api_token import verify_token
from app.services.auth import InvalidTokenError, decode_access_token


SESSION_COOKIE_NAME = "fm_session"

DbDep = Annotated[Session, Depends(get_db)]


def _try_cookie(db: Session, cookie: str | None) -> User | None:
    if not cookie:
        return None
    try:
        payload = decode_access_token(cookie)
    except InvalidTokenError:
        return None
    username = payload.get("sub")
    if not username:
        return None
    return db.execute(select(User).where(User.username == username)).scalar_one_or_none()


def _try_bearer(db: Session, authorization: str | None) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    plain = authorization[7:].strip()
    return verify_token(db, plain)


def current_user(
    db: DbDep,
    fm_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """spec § 10.1 + § 10.2 双通道认证。先 cookie,再 Bearer。"""
    user = _try_cookie(db, fm_session)
    if user is not None:
        return user
    user = _try_bearer(db, authorization)
    if user is not None:
        return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid credentials")


CurrentUserDep = Annotated[User, Depends(current_user)]


def bearer_only_user(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """仅 Bearer 认证(给 /api/admin/tokens/verify 用,确保 cookie 不能滥用 verify)。"""
    user = _try_bearer(db, authorization)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid bearer token")
    return user


BearerUserDep = Annotated[User, Depends(bearer_only_user)]
