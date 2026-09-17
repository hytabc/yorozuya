from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from .config import settings


SESSION_MAX_AGE_SECONDS = 24 * 60 * 60
# “自动登录”令牌的绝对有效期上限：无论配置多大都不超过 7 天。
REMEMBER_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    token_version: int


PBKDF2_ITERATIONS = 310_000
# 允许校验的迭代次数范围：下限拦住「被篡改成 1 次」的弱哈希，
# 上限拦住恶意超大迭代造成的 CPU 耗尽。
MIN_PBKDF2_ITERATIONS = 100_000
MAX_PBKDF2_ITERATIONS = 1_000_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        rounds = int(iterations)
        if not MIN_PBKDF2_ITERATIONS <= rounds <= MAX_PBKDF2_ITERATIONS:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.urlsafe_b64decode(salt), rounds
        )
        return hmac.compare_digest(base64.urlsafe_b64encode(digest).decode(), expected)
    except (ValueError, TypeError):
        return False


def password_needs_rehash(encoded: str) -> bool:
    """哈希迭代次数低于当前标准时，登录成功后顺带升级。"""
    try:
        algorithm, iterations, _, _ = encoded.split("$", 3)
        return algorithm != "pbkdf2_sha256" or int(iterations) < PBKDF2_ITERATIONS
    except (ValueError, TypeError):
        return True


# 登录时对不存在的账号也执行一次同成本的校验，抹平「账号是否存在」的耗时差异。
_TIMING_EQUALIZER_HASH = hash_password("yorozuya-timing-equalizer")


def equalize_password_check(password: str) -> None:
    """仅用于让「账号不存在」与「密码错误」两条分支耗时一致，返回值无意义。"""
    verify_password(password, _TIMING_EQUALIZER_HASH)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _token_lifetime(remember: bool) -> int:
    if not remember:
        return min(settings.access_token_minutes * 60, SESSION_MAX_AGE_SECONDS)
    return min(settings.remember_token_days * 24 * 60 * 60, REMEMBER_MAX_AGE_SECONDS)


def create_access_token(user_id: int, token_version: int = 0, remember: bool = False) -> str:
    issued_at = int(time.time())
    payload_data = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": issued_at,
        "exp": issued_at + _token_lifetime(remember),
    }
    if remember:
        payload_data["rm"] = True
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64encode(json.dumps(payload_data, separators=(",", ":")).encode())
    signature = _b64encode(hmac.new(settings.secret_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_access_token(token: str) -> TokenPayload:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态无效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        header, payload, signature = token.split(".")
        expected = _b64encode(
            hmac.new(settings.secret_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise credentials_error
        data: dict[str, Any] = json.loads(_b64decode(payload))
        now = int(time.time())
        issued_at = int(data["iat"])
        # “自动登录”令牌（rm）允许 7 天，其余令牌维持 24 小时上限。
        ceiling = REMEMBER_MAX_AGE_SECONDS if data.get("rm") else SESSION_MAX_AGE_SECONDS
        if issued_at > now or now - issued_at >= ceiling or int(data["exp"]) <= now:
            raise credentials_error
        # 旧格式令牌没有 ver 字段，视为 0，与历史账号的 token_version 默认值一致。
        return TokenPayload(user_id=int(data["sub"]), token_version=int(data.get("ver", 0)))
    except (TypeError, ValueError, KeyError, OverflowError, json.JSONDecodeError, binascii.Error):
        raise credentials_error
