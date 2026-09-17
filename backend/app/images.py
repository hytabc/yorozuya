"""上传图片的净化：解码校验、像素上限、按方向摆正、剥元数据、统一静态输出。

以前的上传链路只嗅探文件头魔数就把原始字节原样落盘，带来两类问题：

- 原始 EXIF（含 GPS 坐标、设备型号、拍摄时间）会随图片一起公开；
- 超大像素的「压缩炸弹」（例如几 KB 的 PNG 声明 30000×30000）会直接发给访问者
  与审核者的浏览器，拖垮对方客户端。

这里用 Pillow 真正解码一次再以受控格式重新编码输出：
解码前先按文件头判断尺寸，超过 ``MAX_IMAGE_PIXELS`` 直接拒绝（不把 CPU 花在解码炸弹上）；
``exif_transpose`` 按拍摄方向摆正后丢弃全部元数据（编码时不传 exif / icc_profile）；
长边超过 ``MAX_IMAGE_EDGE`` 时等比缩小；动图只取首帧，输出恒为静态 PNG 或 JPEG。
"""

from __future__ import annotations

from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

# 单张图片的像素上限：约 25 MP，远高于手机/相机常用尺寸，但能挡住压缩炸弹。
MAX_IMAGE_PIXELS = 25_000_000
# 长边上限：超过则等比缩小，避免把超大图传给访问者。
MAX_IMAGE_EDGE = 2560
JPEG_QUALITY = 85

# 允许的输入格式（魔数嗅探白名单）。
IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)
# 头像 / 故事配图 / 地图实拍只接受 PNG 与 JPG。
AVATAR_SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
)

FORMAT_HINT_ALL = "仅支持 JPEG、PNG、GIF 或 WebP 图片"
UNREADABLE_DETAIL = "无法解析的图片，请重新选择文件"
TOO_MANY_PIXELS_DETAIL = "图片像素过大，请压缩后再上传"


def sniff_extension(content: bytes, signatures=IMAGE_SIGNATURES) -> str | None:
    """按文件头魔数判断真实格式，返回期望扩展名；不在白名单内返回 None。"""
    for signature, extension in signatures:
        if content.startswith(signature):
            return extension
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp"
    return None


def _keeps_alpha(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA"):
        return True
    if image.mode == "P":
        return "transparency" in image.info
    return False


def normalize_image(
    content: bytes,
    *,
    allowed=IMAGE_SIGNATURES,
    format_hint: str = FORMAT_HINT_ALL,
) -> tuple[str, bytes]:
    """把上传的原始图片转成干净的静态图片，返回（扩展名，字节内容）。"""
    if sniff_extension(content, allowed) is None:
        raise HTTPException(status_code=422, detail=format_hint)
    # 只读文件头拿尺寸：压缩炸弹在解码前就被挡掉。
    try:
        with Image.open(BytesIO(content)) as probe:
            width, height = probe.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(status_code=422, detail=UNREADABLE_DETAIL) from error
    if width * height > MAX_IMAGE_PIXELS:
        raise HTTPException(status_code=422, detail=TOO_MANY_PIXELS_DETAIL)

    try:
        with Image.open(BytesIO(content)) as image:
            image.seek(0)  # 动图只保留首帧，避免把帧数与体积一起带出去
            source = ImageOps.exif_transpose(image)  # 按拍摄方向摆正（随后元数据全部丢弃）
            keeps_alpha = _keeps_alpha(source)
            converted = source.convert("RGBA" if keeps_alpha else "RGB")
            converted.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
            buffer = BytesIO()
            if keeps_alpha:
                converted.save(buffer, format="PNG", optimize=True)
                extension = ".png"
            else:
                converted.save(
                    buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True
                )
                extension = ".jpg"
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(status_code=422, detail=UNREADABLE_DETAIL) from error
    return extension, buffer.getvalue()
