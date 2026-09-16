"""媒体分区与签名访问。

上传的图片分两个区存放：

- **公开区**（``settings.sugar_upload_path``）：只有已过审（``is_visible`` / ``avatar_visible``
  为真）的文件，由 ``/uploads`` 静态托管，URL 形如 ``/uploads/sugar/xxx.jpg``。
- **私有区**（``settings.media_private_path``）：待审与被屏蔽的文件，不参与任何静态挂载，
  只能凭 ``/api/media/{key}?exp=&sig=`` 的短时签名访问。

为什么用签名而不是登录校验：``<img>`` 标签带不了 ``Authorization`` 头，服务端拿不到
Bearer 令牌。因此签名本身就是访问控制，同时让「审核驳回后旧链接立即失效」成为可能
—— 审核翻转时把文件从一个区搬到另一个区，旧的公开 URL 直接 404。

``file_path`` 列里始终只存**逻辑 key**（如 ``sugar/xxx.jpg``），所在区由可见性推导，
因此改可见性和搬文件是一次原子操作，不需要改库里的路径。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import shutil
import time
from pathlib import Path

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
    return hmac.compare_digest(signature, sign_media_signature(key, expires_at))


def media_url(key: str | None, *, public: bool) -> str | None:
    if not key:
        return None
    if public:
        return f"{PUBLIC_URL_PREFIX}{key}"
    return sign_media_url(key)


def storage_file(key: str, *, public: bool) -> Path | None:
    """把相对 key 解析成指定区内的绝对路径；越界（``..``、绝对路径）返回 None。"""
    if not key or key.startswith("/") or "\\" in key:
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
    """把文件放到与可见性匹配的区。

    幂等：已在目标区则不动；在另一个区则搬过去；两处都没有则忽略。
    启动对账与审核翻转都走这里，因此搬移失败只记日志，不影响业务请求。
    """
    target = storage_file(key, public=public)
    source = storage_file(key, public=not public)
    if target is None or source is None:
        return
    if target.is_file() or not source.is_file():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    except OSError as error:  # noqa: BLE001 —— 搬移失败不能把业务请求带崩，但要留痕
        logger.warning("媒体分区搬移失败 %s -> %s：%s", source, target, error)


def delete_media(key: str) -> None:
    """删除文件（两个区都尝试），用于记录被删除后的磁盘清理。"""
    for public in (True, False):
        path = storage_file(key, public=public)
        if path is None:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as error:  # noqa: BLE001 —— 清理失败不应阻塞删除接口
            logger.warning("媒体文件删除失败 %s：%s", path, error)
