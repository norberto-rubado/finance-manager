"""认证 service:bcrypt 密码校验 + JWT 签发 / 解析(spec § 10.1)。

本模块**不接 DB,不接 HTTP**,纯函数,便于单元测试。Task 7 的端点调用本服务。
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.hash import bcrypt as bcrypt_hash

from app.core.config import get_settings


_ALGO = "HS256"


class InvalidTokenError(ValueError):
    """JWT 校验失败(过期 / 篡改 / 格式错)。HTTP 层可转 401。"""


def verify_password(plain: str, hashed: str) -> bool:
    """密码校验。无效 hash 返回 False(不抛错,避免 user enum 通过 5xx 区分)。"""
    if not plain or not hashed:
        return False
    try:
        return bcrypt_hash.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(subject: str, expires_minutes: int = 60 * 24 * 30) -> str:
    """签发 JWT,默认 30 天有效(spec § 10.1 cookie 30 天)。

    expires_minutes=0 时 token 立即过期(测试用)。
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGO)


def decode_access_token(token: str) -> dict[str, Any]:
    """校验 + 解析 JWT。失败抛 InvalidTokenError。"""
    if not token or not isinstance(token, str):
        raise InvalidTokenError("token is empty")
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_ALGO])
    except JWTError as e:
        raise InvalidTokenError(str(e)) from e
