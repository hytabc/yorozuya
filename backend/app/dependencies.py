from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserRole
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)
SESSION_COOKIE = "wsw_session"
CSRF_COOKIE = "wsw_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _token_from_request(request: Request, credentials: HTTPAuthorizationCredentials | None) -> tuple[str | None, bool]:
    if credentials is not None:
        return credentials.credentials, False
    return request.cookies.get(SESSION_COOKIE), True


def _require_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    token = request.cookies.get(CSRF_COOKIE)
    supplied = request.headers.get(CSRF_HEADER)
    if not token or not supplied or not hmac.compare_digest(token, supplied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="安全校验失败，请刷新页面后重试")


def _authenticated_user(
    request: Request, credentials: HTTPAuthorizationCredentials | None, db: Session, *, optional: bool
) -> User | None:
    token, from_cookie = _token_from_request(request, credentials)
    if not token:
        if optional:
            return None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        user_id, session_version = decode_access_token(token)
    except HTTPException:
        if optional:
            return None
        raise
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.session_version != session_version:
        if optional:
            return None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用或登录已失效")
    if from_cookie:
        _require_csrf(request)
    return user


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    return _authenticated_user(request, credentials, db, optional=False)


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """登录可选：携带有效令牌时返回当前用户，否则返回 None（公开浏览接口用）。"""
    return _authenticated_user(request, credentials, db, optional=True)


def get_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def get_role_manager(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin and user.role != UserRole.STAFF:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
