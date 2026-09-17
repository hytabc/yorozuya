"""媒体分区与签名访问。

上传的图片分两个区存放：

- **公开区**（``settings.sugar_upload_path``）：已过审文件由 ``/uploads`` 提供，
  每次读取仍校验数据库可见性，URL 形如 ``/uploads/sugar/xxx.jpg``。
- **私有区**（``settings.media_private_path``）：待审与被屏蔽的文件，不参与任何静态挂载，
  只能凭 ``/api/media/{key}?exp=&sig=`` 的短时签名访问。

为什么用签名而不是登录校验：``<img>`` 标签带不了 ``Authorization`` 头，服务端拿不到
Bearer 令牌。因此签名本身就是访问控制。注意签名的有效期由 ``MEDIA_TOKEN_TTL_SECONDS``
决定：审核翻转后，已签发的旧私有链接要在 TTL 到期后才失效，因此该值刻意设得较短，
且读取端会回查数据库当前可见性（已过审/已删除的记录立即 404）。

``file_path`` 列里始终只存**逻辑 key**（如 ``sugar/xxx.jpg``），所在区由可见性推导，
文件与数据库无法原子提交；审核失败保持私有状态，公开读取另查数据库可见性。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import shutil
import time
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .config import settings

logger = logging.getLogger("yorozuya.media")

PUBLIC_URL_PREFIX = "/uploads/"
GATED_URL_PREFIX = "/api/media/"
# 允许校验通过的有效期比配置略长，避免签发与校验之间的耗时造成瞬时失效。
EXPIRY_SLACK_SECONDS = 60


def public_root() -> Path:
    return settings.sugar_upload_path


def private_root() -> Path:
    return settings.media_private_path


def root_for(public: bool) -> Path:
    return public_root() if public else private_root()


def sign_media_signature(key: str, expires_at: int) -> str:
    """为「key + 到期时间」生成签名（与 verify_media_signature 成对）。"""
    digest = hmac.new(
        settings.secret_key.encode(), f"media:{key}:{expires_at}".encode(), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()[:22]


def sign_media_url(key: str, ttl_seconds: int | None = None) -> str:
    ttl = settings.media_token_ttl_seconds if ttl_seconds is None else ttl_seconds
    expires_at = int(time.time()) + max(1, ttl)
    return f"{GATED_URL_PREFIX}{key}?exp={expires_at}&sig={sign_media_signature(key, expires_at)}"


def verify_media_signature(key: str, expires_at: int, signature: str) -> bool:
    """校验签名与有效期：过期、超前（他人预签发）、篡改一律不通过。"""
    now = int(time.time())
    if expires_at < now or expires_at > now + settings.media_token_ttl_seconds + EXPIRY_SLACK_SECONDS:
        return False
    # 必须比较 bytes：compare_digest 对含非 ASCII 的 str 会抛 TypeError（未捕获即 500），
    # 攻击者用 ?sig=é 这类参数即可触发。
    return hmac.compare_digest(
        signature.encode("utf-8"), sign_media_signature(key, expires_at).encode("utf-8")
    )


def media_url(key: str | None, *, public: bool) -> str | None:
    if not key:
        return None
    if public:
        return f"{PUBLIC_URL_PREFIX}{key}"
    return sign_media_url(key)


def storage_file(key: str, *, public: bool) -> Path | None:
    """把相对 key 解析成指定区内的绝对路径；越界（``..``、绝对路径）返回 None。"""
    if not key or key.startswith("/") or "\\" in key or "\x00" in key:
        return None
    root = root_for(public).resolve()
    candidate = (root / key).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate


def write_media(key: str, content: bytes, *, public: bool) -> Path:
    """把新文件写进与初始可见性匹配的区。"""
    destination = storage_file(key, public=public)
    if destination is None:
        raise ValueError(f"非法媒体路径：{key}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def place_media(key: str, *, public: bool) -> None:
    """严格搬区：失败不能报告成功；两区都有副本时清除错误区副本。"""
    target = storage_file(key, public=public)
    source = storage_file(key, public=not public)
    if target is None or source is None:
        raise HTTPException(status_code=503, detail="媒体路径异常，请联系管理员")
    try:
        if target.is_file():
            source.unlink(missing_ok=True)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
    except OSError as error:
        logger.exception("媒体分区操作失败，需对账：%s", key)
        raise HTTPException(status_code=503, detail="媒体文件操作失败，请稍后重试或联系管理员") from error


def commit_moderation(db: Session, key: str, *, public: bool) -> None:
    """搬区成功才提交审核；提交失败时尽可能收回公开文件。"""
    try:
        place_media(key, public=public)
        db.commit()
    except Exception as error:
        logger.exception("媒体审核未提交，需核对状态：%s", key)
        db.rollback()
        # 不恢复公开状态。即使文件系统补偿也失败，公开读取仍检查数据库。
        try:
            place_media(key, public=False)
        except HTTPException:
            logger.exception("审核补偿失败，需对账：%s", key)
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(status_code=503, detail="媒体审核保存失败，请稍后重试或联系管理员") from error


def delete_media(key: str) -> None:
    """先撤回公开副本再删除；失败保留数据库记录以便重试。"""
    place_media(key, public=False)
    path = storage_file(key, public=False)
    if path is None:
        raise HTTPException(status_code=503, detail="媒体路径异常，请联系管理员")
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        logger.exception("媒体删除失败，需重试：%s", key)
        raise HTTPException(status_code=503, detail="媒体文件删除失败，请稍后重试或联系管理员") from error
