"""登录/注册人机验证：站内图形验证码（builtin）与 Cloudflare Turnstile（turnstile）。

- builtin：Pillow 生成带干扰的 4 位字符图片，答案存进程内存（一次性消费 + 限时过期）。
- turnstile：前端拿到 token 后由服务端调用 Cloudflare siteverify 校验（fail-closed）。
- 通过 CAPTCHA_PROVIDER 切换；CAPTCHA_ENABLED=false 可整体关闭。
- pytest 下自动跳过校验（与 ratelimit.enforce 一致），避免干扰既有用例。

Pillow 采用延迟导入：未安装/未启用 builtin 时不影响应用启动与其它 provider。
"""

from __future__ import annotations

import logging
import random
import secrets
import sys
import threading
import time
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, Request, status

from .config import settings
from .ratelimit import client_ip

logger = logging.getLogger("yorozuya.captcha")

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# 去掉易混淆字符（0/O、1/l/I 等），降低误读率。
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 4
_IMAGE_SIZE = (140, 48)
_PRUNE_INTERVAL_SECONDS = 60.0


def captcha_required() -> bool:
    """是否需要强制校验验证码；pytest 下关闭，避免既有用例都要构造验证码。"""
    return settings.captcha_enabled and "pytest" not in sys.modules


def _normalize(code: str) -> str:
    return (code or "").strip().upper()


class CaptchaStore:
    """builtin 验证码答案的内存存储：一次性消费 + 过期清理（本站单进程部署）。"""

    def __init__(self) -> None:
        self._answers: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()
        self._last_prune = time.monotonic()

    def issue(self, answer: str) -> str:
        captcha_id = secrets.token_urlsafe(24)
        expires_at = time.monotonic() + settings.captcha_ttl_seconds
        with self._lock:
            self._answers[captcha_id] = (_normalize(answer), expires_at)
            self._prune(time.monotonic())
        return captcha_id

    def consume(self, captcha_id: str, code: str) -> bool:
        """取出即作废，返回是否匹配。"""
        with self._lock:
            self._prune(time.monotonic())
            entry = self._answers.pop(captcha_id, None)
        if entry is None:
            return False
        expected, expires_at = entry
        if time.monotonic() > expires_at:
            return False
        return secrets.compare_digest(expected, _normalize(code))

    def peek(self, captcha_id: str) -> str | None:
        """仅供测试：读取答案而不消费。"""
        with self._lock:
            entry = self._answers.get(captcha_id)
        return entry[0] if entry else None

    def _prune(self, now: float) -> None:
        if now - self._last_prune < _PRUNE_INTERVAL_SECONDS:
            return
        self._last_prune = now
        for key in [key for key, (_, expires_at) in self._answers.items() if expires_at <= now]:
            del self._answers[key]


captcha_store = CaptchaStore()


def _load_font(size: int):
    from PIL import ImageFont

    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # 旧版 Pillow 的 load_default 不支持 size
        return ImageFont.load_default()


def create_image_captcha() -> tuple[str, bytes]:
    """生成一张 4 位字符验证码图片，返回 (captcha_id, png_bytes)。"""
    from PIL import Image, ImageDraw

    resampling = getattr(Image, "Resampling", Image)
    answer = "".join(random.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
    width, height = _IMAGE_SIZE
    image = Image.new("RGB", (width, height), (245, 247, 246))
    draw = ImageDraw.Draw(image)
    font = _load_font(30)

    for _ in range(6):
        draw.line(
            [
                (random.randrange(width), random.randrange(height)),
                (random.randrange(width), random.randrange(height)),
            ],
            fill=(random.randint(150, 200), random.randint(160, 200), random.randint(150, 195)),
            width=1,
        )
    for _ in range(140):
        draw.point(
            (random.randrange(width), random.randrange(height)),
            fill=(random.randint(180, 220),) * 3,
        )

    step = width / (_CODE_LENGTH + 1)
    for index, char in enumerate(answer):
        char_image = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
        ImageDraw.Draw(char_image).text(
            (6, 4), char, font=font, fill=(random.randint(20, 70),) * 3
        )
        char_image = char_image.rotate(
            random.uniform(-22, 22), resample=resampling.BICUBIC, expand=False
        )
        image.paste(char_image, (int(step * (index + 1) - 20), random.randint(2, 6)), char_image)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return captcha_store.issue(answer), buffer.getvalue()


async def verify_turnstile(token: str, remote_ip: str | None) -> None:
    """调用 Cloudflare siteverify 校验 Turnstile token；任何异常都视为不通过。"""
    import httpx

    if not settings.turnstile_secret_key:
        logger.error("未配置 TURNSTILE_SECRET_KEY，Turnstile 校验无法通过")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="人机验证未正确配置，请联系管理员")
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先完成人机验证")
    data = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip and remote_ip != "unknown":
        data["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(TURNSTILE_VERIFY_URL, data=data)
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 —— 对用户统一返回友好错误
        logger.warning("Turnstile 校验请求失败: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="人机验证服务暂时不可用，请稍后重试")
    if not payload.get("success"):
        logger.info("Turnstile 校验未通过: %s", payload.get("error-codes"))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="人机验证未通过，请重试")


async def verify_captcha(request: Request, captcha_id: str, captcha_code: str) -> None:
    """按配置的 provider 校验人机验证；未启用时直接放行。"""
    if not captcha_required():
        return
    if settings.captcha_provider == "turnstile":
        await verify_turnstile(captcha_code, client_ip(request))
        return
    if not captcha_id or not captcha_store.consume(captcha_id, captcha_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已失效")


def peek_answer(captcha_id: str) -> str | None:
    """仅测试使用：读取 builtin 验证码答案。"""
    return captcha_store.peek(captcha_id)
