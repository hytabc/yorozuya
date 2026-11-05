"""版本更新公告的确认记录。

版本内容本身在前端 ``public/versions/versions.json``（随发布一起上线），
服务端只记住「这个账号确认看到过哪一版」：记在账号上而不是浏览器本地，
换设备或清缓存后不会重复打扰；版本号变化时前端会再次弹出。

与 ``onboarding`` 的区别：这里存的是版本号字符串，按数字段比较"只前进不后退"，
迟到的旧版本请求不会把记录降回去，也不会因为补改同一版的说明而重新打扰用户。
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import get_authenticated_user
from .models import User
from .ratelimit import enforce
from .schemas import VersionAckOut, VersionAckRequest

router = APIRouter(prefix="/api", tags=["version-notes"])

_DIGITS = re.compile(r"\d+")


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in _DIGITS.findall(value or ""))


def _is_newer(candidate: str, current: str | None) -> bool:
    """候选版本是否比已记录的新；没有记录时一律接受。"""
    if not current:
        return True
    candidate_key = _version_key(candidate)
    current_key = _version_key(current)
    if candidate_key and current_key:
        return candidate_key > current_key
    if candidate_key and not current_key:
        # 旧记录不是数字版本（历史脏数据），用规范版本号覆盖一次。
        return True
    return False


@router.post("/version-ack", response_model=VersionAckOut)
def acknowledge_version(
    payload: VersionAckRequest,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """记下「已确认看到当前版本」。只前进不后退，重复提交幂等。

    刻意用 ``get_authenticated_user``：这只是一条界面状态，未验证邮箱的账号
    也会看到弹窗，不该因为邮箱闸门让确认请求 403、导致弹窗关不掉。
    """
    enforce("version-ack", str(user.id), 20, 600)
    version = payload.version.strip()
    if version and _is_newer(version, user.version_ack):
        user.version_ack = version
        db.commit()
        db.refresh(user)
    return VersionAckOut(version_ack=user.version_ack)
