"""API token service — spec § 10.2。

token 生成时返回明文(仅这一次);DB 仅存 sha256 hash;
验证调 verify_token(plain) → User | None,顺手更新 last_used_at。
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApiToken, User


def hash_token(plain: str) -> str:
    """sha256 hex digest(64 chars)。"""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def create_api_token(
    db: Session, *, user_id: int, name: str, scopes: str = "read,write",
) -> tuple[str, ApiToken]:
    """生成新 token 并落库。返回 (plain_token, ApiToken_obj)。

    plain 仅在调用方可见这一次;DB 中只存 token_hash。
    """
    plain = secrets.token_urlsafe(32)
    token = ApiToken(
        user_id=user_id,
        name=name,
        token_hash=hash_token(plain),
        scopes=scopes,
    )
    db.add(token); db.flush()
    return plain, token


def verify_token(db: Session, plain: str) -> User | None:
    """Bearer 验证:plain → User(若有效未吊销)否则 None。

    成功时顺手更新 last_used_at。失败不抛,返回 None。
    """
    if not plain:
        return None
    digest = hash_token(plain)
    token = db.execute(
        select(ApiToken).where(
            ApiToken.token_hash == digest,
            ApiToken.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if token is None:
        return None
    user = db.execute(
        select(User).where(User.id == token.user_id)
    ).scalar_one_or_none()
    if user is None:
        return None
    # 更新 last_used_at(细粒度审计)
    token.last_used_at = datetime.now(timezone.utc)
    db.flush()
    return user


def revoke_token(db: Session, *, token_id: int, user_id: int) -> bool:
    """吊销:仅当 token 属于本 user_id。返回 True 表示找到并标记;False 表示没找到。

    幂等:若 token 已吊销,不覆盖 revoked_at。
    """
    token = db.execute(
        select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == user_id,
        )
    ).scalar_one_or_none()
    if token is None:
        return False
    if token.revoked_at is None:
        token.revoked_at = datetime.now(timezone.utc)
        db.flush()
    return True


def list_tokens(db: Session, *, user_id: int) -> list[ApiToken]:
    """列出 user 的所有 tokens(含已吊销;按 created_at DESC)。"""
    return list(db.execute(
        select(ApiToken).where(ApiToken.user_id == user_id)
        .order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
    ).scalars().all())
