"""登录、注册、注销与当前登录态。"""

import hmac
import sqlite3
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import settings
from app.db.users import (
    create_session,
    create_user,
    delete_session,
    get_user_by_username,
    purge_expired_sessions,
)
from app.schemas.auth import AuthState, AuthUser, LoginRequest, RegisterRequest
from app.services.auth import (
    COOKIE_NAME,
    current_user,
    digest_token,
    hash_password,
    new_token,
    verify_password,
)
from app.services.risks.dates import now_in_timezone

router = APIRouter(tags=["登录注册"])


def _issue_session(response: Response, user_id: int, secure: bool) -> None:
    now = now_in_timezone()
    expires_at = now + timedelta(days=settings.auth_session_days)
    token = new_token()
    purge_expired_sessions(now.isoformat())
    create_session(
        user_id, digest_token(token), now.isoformat(), expires_at.isoformat()
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.auth_session_days * 86400,
        httponly=True,
        samesite="lax",
        # 按实际访问协议决定：HTTPS（含平台代理）加 Secure，本地 http 不加，
        # 否则本地 compose 演示会出现「登录成功但 Cookie 不保存」。
        secure=secure,
        path="/",
    )


def _is_https(request: Request) -> bool:
    return request.url.scheme == "https"


def _state(request: Request) -> AuthState:
    if not settings.auth_enabled:
        return AuthState(enabled=False)
    user = current_user(request)
    return AuthState(
        enabled=True,
        authenticated=user is not None,
        user=AuthUser(**user) if user else None,
    )


@router.get("/auth/me", response_model=AuthState)
def read_auth_state(request: Request) -> AuthState:
    return _state(request)


@router.post("/auth/register", response_model=AuthState)
def register(payload: RegisterRequest, request: Request, response: Response) -> AuthState:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=403,
            detail={"code": "auth_disabled", "message": "当前环境未开启登录注册。"},
        )
    if not settings.auth_invite_code:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "invite_not_configured",
                "message": "服务端未配置邀请码，暂时无法注册。",
            },
        )
    if not hmac.compare_digest(payload.invite_code, settings.auth_invite_code):
        raise HTTPException(
            status_code=403,
            detail={"code": "invalid_invite", "message": "邀请码不正确。"},
        )
    if get_user_by_username(payload.username) is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "username_taken", "message": "该用户名已被注册。"},
        )
    try:
        user = create_user(
            payload.username,
            hash_password(payload.password),
            now_in_timezone().isoformat(timespec="milliseconds"),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail={"code": "username_taken", "message": "该用户名已被注册。"},
        ) from None
    _issue_session(response, user["id"], _is_https(request))
    # 响应里的 Cookie 尚未进入 request.cookies，这里直接构造登录成功状态。
    return AuthState(
        enabled=True,
        authenticated=True,
        user=AuthUser(id=user["id"], username=user["username"]),
    )


@router.post("/auth/login", response_model=AuthState)
def login(payload: LoginRequest, request: Request, response: Response) -> AuthState:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=403,
            detail={"code": "auth_disabled", "message": "当前环境未开启登录。"},
        )
    user = get_user_by_username(payload.username.strip())
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "用户名或密码错误。"},
        )
    _issue_session(response, user["id"], _is_https(request))
    return AuthState(
        enabled=True,
        authenticated=True,
        user=AuthUser(id=user["id"], username=user["username"]),
    )


@router.post("/auth/logout", response_model=AuthState)
def logout(request: Request, response: Response) -> AuthState:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        delete_session(digest_token(token))
    response.delete_cookie(COOKIE_NAME, path="/")
    return _state(request)
