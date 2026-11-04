"""生成站内色系的 Logo 与横幅素材。

用法：python3 scripts/build-brand-assets.py
输出：frontend/public/brand/*.png 与 frontend/public/favicon-32.png / apple-touch-icon.png

设计原则：保留原线稿「屋顶 + 心 + 漩涡」造型，主色改为站内绿 (#237a57)，
蓝色 (#286c86) 只做渐变点缀；背景使用站内纸白，横幅按比例留出标题区。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "yorozuya.jpg"
OUT = ROOT / "frontend" / "public" / "brand"
PUBLIC = ROOT / "frontend" / "public"

GREEN = (35, 122, 87)
BLUE = (40, 108, 134)
PAPER = (243, 245, 242)
INK = (24, 32, 29)
MUTED = (105, 115, 110)

FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"


def recolor(source: Image.Image) -> Image.Image:
    """把蓝色线稿映射成站内绿，保留抗锯齿边缘的明暗层次。"""
    image = source.convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            if b > r + 20 and b > g:  # 蓝色像素
                t = min(1.0, max(0.0, (b - r) / 220))
                pixels[x, y] = (
                    int(GREEN[0] * (1 - t) + BLUE[0] * t),
                    int(GREEN[1] * (1 - t) + BLUE[1] * t),
                    int(GREEN[2] * (1 - t) + BLUE[2] * t),
                    a,
                )
    return image


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def fit(image: Image.Image, box: tuple[int, int]) -> Image.Image:
    scale = min(box[0] / image.width, box[1] / image.height)
    return image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.LANCZOS)


def square(logo: Image.Image, size: int, target: Path) -> None:
    canvas = Image.new("RGBA", (size, size), (*PAPER, 255))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((size * 0.04, size * 0.04, size * 0.96, size * 0.96), outline=(*GREEN, 40), width=max(2, size // 120))
    scaled = fit(logo, (int(size * 0.8), int(size * 0.8)))
    canvas.alpha_composite(scaled, ((size - scaled.width) // 2, (size - scaled.height) // 2))
    canvas.convert("RGB").save(target, optimize=True)


def banner(logo: Image.Image, size: tuple[int, int], target: Path, title: str, subtitle: str) -> None:
    canvas = Image.new("RGBA", size, (*PAPER, 255))
    draw = ImageDraw.Draw(canvas)
    w, h = size
    # 背景：淡绿圆形 + 斜向细线，避免大面积空白。
    for ratio, color in ((0.62, (*GREEN, 16)), (0.46, (*BLUE, 14))):
        r = int(min(w, h) * ratio)
        draw.ellipse((int(w * 0.72) - r // 2, h // 2 - r // 2, int(w * 0.72) + r // 2, h // 2 + r // 2), fill=color)
    for offset in range(-h, w, max(24, h // 12)):
        draw.line((offset, h, offset + h, 0), fill=(*GREEN, 10), width=max(1, h // 400))

    icon = fit(logo, (int(min(w, h) * 0.52), int(min(w, h) * 0.52)))
    canvas.alpha_composite(icon, (int(w * 0.06), (h - icon.height) // 2))

    title_size = max(28, int(h * 0.12))
    sub_size = max(16, int(h * 0.05))
    text_x = int(w * 0.06) + icon.width + int(w * 0.03)
    draw.text((text_x, h // 2 - title_size), title, font=font(title_size), fill=INK)
    draw.text((text_x, h // 2 + int(title_size * 0.25)), subtitle, font=font(sub_size), fill=MUTED)
    canvas.convert("RGB").save(target, optimize=True)


def horizontal(logo: Image.Image, target: Path) -> None:
    canvas = Image.new("RGBA", (720, 180), (0, 0, 0, 0))
    icon = fit(logo, (150, 150))
    canvas.alpha_composite(icon, (14, 15))
    draw = ImageDraw.Draw(canvas)
    draw.text((180, 78), "VRC 万事屋", font=font(46), fill=(*GREEN, 255))
    canvas.save(target, optimize=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    logo = recolor(Image.open(SOURCE))
    square(logo, 1024, OUT / "logo-square-1024.png")
    square(logo, 512, OUT / "logo-square-512.png")
    square(logo, 180, PUBLIC / "apple-touch-icon.png")
    square(logo, 32, PUBLIC / "favicon-32.png")
    horizontal(logo, OUT / "logo-horizontal.png")
    banner(logo, (1920, 1080), OUT / "banner-16x9.png", "VRC 万事屋", "委托 · 协作 · 被看见")
    banner(logo, (1600, 1200), OUT / "banner-4x3.png", "VRC 万事屋", "发布委托，遇见靠谱的人")
    banner(logo, (2560, 1080), OUT / "banner-21x9.png", "VRC 万事屋", "委托大厅 · 评价与积分")
    banner(logo, (1640, 856), OUT / "banner-vrc-group-1640x856.png", "VRC 万事屋", "VRChat 社区委托站")
    banner(logo, (1920, 1080), PUBLIC / "og-16x9.png", "VRC 万事屋", "委托 · 协作 · 被看见")
    print("brand assets written to", OUT)


if __name__ == "__main__":
    main()
