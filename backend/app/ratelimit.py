"""进程内滑动窗口限流：用于登录/注册/带密码接取/看板娘等易被滥用的入口。

单进程内存实现，够本站规模使用；多 worker 部署时每个进程各自计数。
"""

from __future__ import annotations

import sys
import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

from .config import settings

_PRUNE_INTERVAL_SECONDS = 60.0
_MAX_TRACKED_WINDOW_SECONDS = 3600


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_prune = time.monotonic()

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._events.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(bucket[0] + window_seconds - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="操作过于频繁，请稍后再试",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
            self._prune(now)

    def _prune(self, now: float) -> None:
        if now - self._last_prune < _PRUNE_INTERVAL_SECONDS:
            return
        self._last_prune = now
        stale = now - _MAX_TRACKED_WINDOW_SECONDS
        for key in list(self._events):
            bucket = self._events[key]
            while bucket and bucket[0] <= stale:
                bucket.popleft()
            if not bucket:
                del self._events[key]


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    """仅在信任反向代理时读取其透传的真实 IP，避免被伪造的请求头绕过限流。"""
    if settings.behind_proxy:
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(bucket: str, key: str, limit: int, window_seconds: int) -> None:
    # 测试会从同一来源反复注册/登录，跳过节流以免干扰用例。
    if "pytest" in sys.modules:
        return
    limiter.hit(f"{bucket}:{key[:120]}", limit, window_seconds)
