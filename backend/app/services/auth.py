"""密码哈希、会话令牌与接口鉴权。

约束：
- 只使用标准库，不引入 bcrypt / pyjwt 等依赖；
- 密码用 PBKDF2-HMAC-SHA256 + 每用户随机盐；
- 会话用随机令牌，数据库只存 SHA-256 摘要。
"""

import base64
import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request

from app.core.config import settings
from app.db.users import get_user_by_session
from app.services.risks.dates import now_in_timezone

COOKIE_NAME = "taskradar_session"
_HASH_ITERATIONS = 200_000
_HASH_SCHEME = "pbkdf2_sha256"

# entrypoint 在容器内通过 127.0.0.1 调用这两个接口做自检与空库播种，
# 该调用不经过 nginx，因此没有 X-Forwarded-For。仅对这两个路径放行，
# 外部请求经 nginx 转发时一定带该头，仍需登录。
_INTERNAL_PATHS = {"/api/demo/status", "/api/demo/seed"}


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _HASH_ITERATIONS
    )
    return f"{_HASH_SCHEME}${_HASH_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_b64, digest_b64 = stored.split("$")
        if scheme != _HASH_SCHEME:
            return False
        salt = _b64decode(salt_b64)
        expected = _b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_user(request: Request) -> dict | None:
    """读取当前登录用户；未登录、会话过期或已注销都返回 None。"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return get_user_by_session(digest_token(token))


def require_auth(request: Request) -> dict | None:
    """受保护路由的依赖：关闭登录时放行，开启后必须携带有效会话。"""
    if not settings.auth_enabled:
        return None
    if (
        request.url.path in _INTERNAL_PATHS
        and not request.headers.get("x-forwarded-for")
    ):
        return None
    if current_user(request) is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "请先登录后再操作。"},
        )
    return None


def session_expiry_iso() -> str:
    from datetime import timedelta

    return (now_in_timezone() + timedelta(days=settings.auth_session_days)).isoformat()
