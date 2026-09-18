"""登录/注册人机验证：站内图形验证码（builtin）、点击图形验证码（click）与 Cloudflare Turnstile（turnstile）。

- builtin：Pillow 生成带干扰的 4 位字符图片，答案存进程内存（一次性消费 + 限时过期）。
- click：Pillow 生成随机图形，按题面「颜色 + 形状 + 大小」依次点击目标；答案（目标中心点与顺序）
  只存服务端，前端仅拿到图片与题面文字，绝不回传坐标；一次性消费 + 限时 + 坐标容差。
- turnstile：前端拿到 token 后由服务端调用 Cloudflare siteverify 校验（fail-closed）。
- 通过 CAPTCHA_PROVIDER 互斥切换；CAPTCHA_ENABLED=false 可整体关闭。
- pytest 下自动跳过校验（与 ratelimit.enforce 一致），避免干扰既有用例。

Pillow 采用延迟导入：未安装/未启用图像类 provider 时不影响应用启动。
"""

from __future__ import annotations

import logging
import math
import random
import secrets
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, Request, status

from .config import settings
from .ratelimit import client_ip, enforce

logger = logging.getLogger("yorozuya.captcha")

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# 去掉易混淆字符（0/O、1/l/I 等），降低误读率。
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 4
_IMAGE_SIZE = (140, 48)
_PRUNE_INTERVAL_SECONDS = 60.0

# ── click（点击图形）验证码参数 ──
_CLICK_IMAGE_SIZE = (320, 200)
_CLICK_MIN_TARGETS = 2
_CLICK_MAX_TARGETS = 4
_CLICK_DECOY_RANGE = (3, 5)
_CLICK_CODE_MAX_LENGTH = 512
_CLICK_PLACEMENT_GAP = 4

# 形状 / 大小 / 颜色字典：中文文案用于题面，英文键用于去重与绘制。
_SHAPES = ("circle", "triangle", "square", "diamond", "star")
_SHAPE_LABELS = {
    "circle": "圆形",
    "triangle": "三角形",
    "square": "方形",
    "diamond": "菱形",
    "star": "星形",
}
_SIZES = ("small", "medium", "large")
_SIZE_LABELS = {"small": "小", "medium": "中", "large": "大"}
_SIZE_RATIOS = {"small": 0.06, "medium": 0.09, "large": 0.12}
_COLORS = (
    ("red", "红色", (214, 45, 45)),
    ("blue", "蓝色", (45, 95, 214)),
    ("green", "绿色", (35, 150, 80)),
    ("orange", "橙色", (232, 140, 30)),
    ("purple", "紫色", (140, 70, 200)),
    ("teal", "青色", (30, 150, 160)),
)


def captcha_required() -> bool:
    """是否需要强制校验验证码；测试模式关闭，避免既有用例都要构造验证码。"""
    return settings.captcha_enabled and not settings.testing


def _normalize(code: str) -> str:
    return (code or "").strip().upper()


@dataclass(frozen=True)
class ClickTarget:
    """click 验证码的一个目标：归一化中心点（0..1）与命中容差半径（归一化）。"""

    x: float
    y: float
    tolerance: float


@dataclass(frozen=True)
class ClickChallenge:
    """click 验证码的服务端答案：按点击顺序排列的目标 + 出题时间。"""

    targets: tuple[ClickTarget, ...]
    prompt: str
    issued_at: float


class CaptchaStore:
    """验证码答案的内存存储：一次性消费 + 过期清理（本站单进程部署）。

    payload 为任意对象：builtin 存归一化后的字符串答案，click 存 ClickChallenge。
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[object, float]] = {}
        self._lock = threading.Lock()
        self._last_prune = time.monotonic()

    def issue(self, payload: object, ttl_seconds: float | None = None) -> str:
        captcha_id = secrets.token_urlsafe(24)
        ttl = settings.captcha_ttl_seconds if ttl_seconds is None else ttl_seconds
        expires_at = time.monotonic() + ttl
        with self._lock:
            self._entries[captcha_id] = (payload, expires_at)
            self._prune(time.monotonic())
        return captcha_id

    def take(self, captcha_id: str) -> object | None:
        """取出即作废：成功时返回 payload，未知/已过期返回 None。"""
        with self._lock:
            self._prune(time.monotonic())
            entry = self._entries.pop(captcha_id, None)
        if entry is None:
            return None
        payload, expires_at = entry
        if time.monotonic() > expires_at:
            return None
        return payload

    def consume_code(self, captcha_id: str, code: str) -> bool:
        """builtin 用：取出并做大小写不敏感的字符串比对。"""
        payload = self.take(captcha_id)
        if not isinstance(payload, str):
            return False
        return secrets.compare_digest(payload, _normalize(code))

    def peek(self, captcha_id: str) -> object | None:
        """仅供测试：读取 payload 而不消费。"""
        with self._lock:
            entry = self._entries.get(captcha_id)
        return entry[0] if entry else None

    def _prune(self, now: float) -> None:
        if now - self._last_prune < _PRUNE_INTERVAL_SECONDS:
            return
        self._last_prune = now
        for key in [key for key, (_, expires_at) in self._entries.items() if expires_at <= now]:
            del self._entries[key]


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
    # 答案用 CSPRNG 生成，不能用 Mersenne-Twister 的 random（可被预测，且干扰线共用同一序列）。
    answer = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
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


def _darken(color: tuple[int, int, int], factor: float = 0.72) -> tuple[int, int, int]:
    return tuple(max(0, int(channel * factor)) for channel in color)


def _star_points(cx: float, cy: float, radius: float) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    for index in range(10):
        angle = -math.pi / 2 + index * math.pi / 5
        radius_i = radius if index % 2 == 0 else radius * 0.45
        coords.append((cx + radius_i * math.cos(angle), cy + radius_i * math.sin(angle)))
    return coords


def _draw_shape(draw, shape: str, cx: float, cy: float, radius: float, color) -> None:
    outline = _darken(color)
    box = [cx - radius, cy - radius, cx + radius, cy + radius]
    if shape == "circle":
        draw.ellipse(box, fill=color, outline=outline, width=2)
    elif shape == "square":
        draw.rectangle(box, fill=color, outline=outline, width=2)
    elif shape == "triangle":
        draw.polygon([(cx, cy - radius), (cx - radius, cy + radius), (cx + radius, cy + radius)],
                     fill=color, outline=outline)
    elif shape == "diamond":
        draw.polygon([(cx, cy - radius), (cx + radius, cy), (cx, cy + radius), (cx - radius, cy)],
                     fill=color, outline=outline)
    else:  # star
        draw.polygon(_star_points(cx, cy, radius), fill=color, outline=outline)


def _grid_layout(total: int) -> tuple[int, int]:
    if total <= 4:
        return 2, 2
    if total <= 6:
        return 3, 2
    return 3, 3


def _place_shapes(rand, width: int, height: int, shapes: list[dict]) -> list[dict]:
    """抖动网格布点：网格保证互不重叠，抖动避免排列过于规整。

    同一格内的偏移上限按该图形半径收窄，使相邻图形的中心距始终 ≥ r_i + r_j + gap。
    """
    cols, rows = _grid_layout(len(shapes))
    cell_w, cell_h = width / cols, height / rows
    cells = [(col, row) for row in range(rows) for col in range(cols)]
    rand.shuffle(cells)
    placed: list[dict] = []
    for (col, row), shape in zip(cells, shapes):
        radius = shape["radius"]
        base_x = (col + 0.5) * cell_w
        base_y = (row + 0.5) * cell_h
        half_x = max(0.0, cell_w / 2 - radius - _CLICK_PLACEMENT_GAP)
        half_y = max(0.0, cell_h / 2 - radius - _CLICK_PLACEMENT_GAP)
        shape["cx"] = base_x + rand.uniform(-half_x, half_x)
        shape["cy"] = base_y + rand.uniform(-half_y, half_y)
        placed.append(shape)
    return placed


def create_click_captcha() -> tuple[str, bytes, str, int]:
    """生成点击图形验证码，返回 (captcha_id, png_bytes, prompt, target_count)。

    答案（目标中心点与顺序）只落在服务端内存，返回值与接口响应均不回传坐标。
    """
    from PIL import Image, ImageDraw

    rand = secrets.SystemRandom()
    width, height = _CLICK_IMAGE_SIZE
    shortest = min(width, height)

    target_count = max(_CLICK_MIN_TARGETS, min(_CLICK_MAX_TARGETS, settings.captcha_click_targets))
    decoys = rand.randint(*_CLICK_DECOY_RANGE)
    total = target_count + decoys

    # 「颜色 + 形状 + 大小」三元组互不相同：题面描述的目标可唯一判定，同色同形状不同大小可作诱饵。
    combos = [
        (shape, size, color)
        for shape in _SHAPES
        for size in _SIZES
        for color in _COLORS
    ]
    picked = rand.sample(combos, total)
    shapes = [
        {
            "shape": shape,
            "size": size,
            "color_key": color[0],
            "color_label": color[1],
            "color": color[2],
            "radius": _SIZE_RATIOS[size] * shortest,
        }
        for shape, size, color in picked
    ]
    shapes = _place_shapes(rand, width, height, shapes)

    targets = rand.sample(shapes, target_count)
    rand.shuffle(targets)
    labels = [
        f"{item['color_label']}的{_SHAPE_LABELS[item['shape']]}（{_SIZE_LABELS[item['size']]}）"
        for item in targets
    ]
    prompt = "请按顺序依次点击：" + "、".join(labels)

    image = Image.new("RGB", (width, height), (247, 249, 248))
    draw = ImageDraw.Draw(image)
    for _ in range(160):
        draw.point(
            (random.randrange(width), random.randrange(height)),
            fill=(random.randint(210, 238),) * 3,
        )
    for _ in range(4):
        draw.line(
            [
                (random.randrange(width), random.randrange(height)),
                (random.randrange(width), random.randrange(height)),
            ],
            fill=(random.randint(205, 230),) * 3,
            width=1,
        )
    for shape in shapes:
        _draw_shape(draw, shape["shape"], shape["cx"], shape["cy"], shape["radius"], shape["color"])

    # 容差取半径的 0.9：覆盖图形内部，又因网格间距足够，不会命中相邻图形。
    click_targets = tuple(
        ClickTarget(
            x=item["cx"] / width,
            y=item["cy"] / height,
            tolerance=item["radius"] * 0.9 / shortest,
        )
        for item in targets
    )
    payload = ClickChallenge(targets=click_targets, prompt=prompt, issued_at=time.monotonic())
    captcha_id = captcha_store.issue(payload)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return captcha_id, buffer.getvalue(), prompt, target_count


def _click_failure() -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已失效")


def _parse_click_code(code: str, expected: int) -> list[tuple[float, float]] | None:
    """解析 "x1,y1;x2,y2" 形式的归一化点击坐标；任何畸形输入返回 None。"""
    if not code or len(code) > _CLICK_CODE_MAX_LENGTH:
        return None
    segments = code.split(";")
    if len(segments) != expected:
        return None
    points: list[tuple[float, float]] = []
    for segment in segments:
        parts = segment.split(",")
        if len(parts) != 2:
            return None
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError:
            return None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return None
        points.append((x, y))
    return points


def verify_click_captcha(request: Request, captcha_id: str, code: str) -> None:
    """校验 click 验证码：按顺序逐点命中容差范围内才算通过；任何异常一律 400。"""
    # 对点击提交单独限流，配合一次性挑战限制暴力枚举尝试次数。
    # 上限与挑战下发（captcha-ip 60/300）一致，避免比 login-ip 更早触发而误伤共享出口 IP。
    enforce("captcha-verify-ip", client_ip(request), 60, 300)
    payload = captcha_store.take(captcha_id) if captcha_id else None
    if not isinstance(payload, ClickChallenge):
        raise _click_failure()
    # 反脚本最短耗时：真实用户不可能在极短时间内完成阅读与点击（测试模式跳过）。
    if not settings.testing and time.monotonic() - payload.issued_at < settings.captcha_click_min_seconds:
        raise _click_failure()
    points = _parse_click_code(code, len(payload.targets))
    if points is None:
        raise _click_failure()
    for (x, y), target in zip(points, payload.targets):
        if math.hypot(x - target.x, y - target.y) > target.tolerance:
            raise _click_failure()


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
    """按实际生效的 provider 校验人机验证；未启用时直接放行。"""
    if not captcha_required():
        return
    provider = settings.captcha_effective_provider
    if provider == "turnstile":
        await verify_turnstile(captcha_code, client_ip(request))
        return
    if provider == "click":
        verify_click_captcha(request, captcha_id, captcha_code)
        return
    if not captcha_id or not captcha_store.consume_code(captcha_id, captcha_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已失效")


def peek_answer(captcha_id: str) -> str | None:
    """仅测试使用：读取 builtin 验证码答案。"""
    payload = captcha_store.peek(captcha_id)
    return payload if isinstance(payload, str) else None


def peek_click_targets(captcha_id: str) -> list[tuple[float, float]] | None:
    """仅测试使用：读取 click 验证码目标中心点（按点击顺序）。"""
    payload = captcha_store.peek(captcha_id)
    if not isinstance(payload, ClickChallenge):
        return None
    return [(target.x, target.y) for target in payload.targets]
