"""邮件发送：SMTP 传输（SSL/STARTTLS 可配）、中文模板与本地 OUTBOX。

- 真实发信用标准库 ``smtplib``（默认 465 + SSL，可改为 587 + STARTTLS），经线程池执行，
  不阻塞事件循环，也**不引入新依赖**（供应链更干净）。
- ``EMAIL_DELIVERY=log``（或 pytest 运行中）不联网：邮件写入 ``OUTBOX`` 并打印到日志，
  本地开发无需配 SMTP，测试也能从中取出验证链接与验证码。
- 邮件服务未配置或发送失败时抛 ``EmailNotConfigured`` / ``EmailDeliveryError``，
  由 ``email_flow.deliver()`` 统一转成 503 —— 这是刻意的 fail-closed：
  宁可不注册，也不能出现「账号建好了但收不到验证信」的死局。

模板约定：用户数据只进正文，绝不进邮件头（防头注入）；HTML 版本统一经 ``html.escape``。
"""

from __future__ import annotations

import html
import logging
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr

from starlette.concurrency import run_in_threadpool

from .config import settings

logger = logging.getLogger("yorozuya.mailer")

BRAND = "万事屋委托站"

# 本地开发/测试用信箱：所有「发出」的邮件都会追加到这里，供测试断言取用。
OUTBOX: list[dict] = []
_OUTBOX_LIMIT = 200


class EmailNotConfigured(RuntimeError):
    """邮件服务未配置：EMAIL_DELIVERY=smtp 但缺少 SMTP 凭据或发件地址。"""


class EmailDeliveryError(RuntimeError):
    """邮件投递失败（网络不可达、中继拒收、认证失败等）。"""


def delivery_is_local() -> bool:
    """是否走本地信箱（不发真邮件）。

    pytest 下强制走本地：测试不应依赖外网，也不该真的给人发信。
    """
    return settings.email_delivery != "smtp" or "pytest" in sys.modules


def mask_email(address: str | None) -> str:
    """展示用掩码：``abcdef@example.com`` → ``ab***@example.com``。"""
    if not address or "@" not in address:
        return ""
    local, _, domain = address.partition("@")
    keep = local[:2] if len(local) > 2 else local[:1]
    return f"{keep}***@{domain}"


def _smtp_send(message: EmailMessage) -> None:
    """按 SMTP_ENCRYPTION 选择连接方式：ssl=直接 TLS（465）；starttls=明文升级（587）；none=不加密。"""
    context = ssl.create_default_context()
    if settings.smtp_encryption == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
            context=context,
        )
    else:
        client = smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
        )
    with client:
        if settings.smtp_encryption == "starttls":
            client.starttls(context=context)
            client.ehlo()
        client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)


async def send_email(
    to: str,
    subject: str,
    text: str,
    html_body: str | None = None,
    *,
    required: bool = True,
) -> bool:
    """发送一封邮件。

    ``required=True``（账号安全类）：失败抛异常，调用方转 503 —— fail-closed。
    ``required=False``（事件通知）：失败只记日志并返回 False，绝不影响业务请求。
    """
    if delivery_is_local():
        OUTBOX.append({"to": to, "subject": subject, "text": text, "html": html_body})
        del OUTBOX[:-_OUTBOX_LIMIT]
        logger.info("[mail:local] to=%s subject=%s\n%s", to, subject, text)
        return True

    if not settings.smtp_ready:
        if required:
            raise EmailNotConfigured("邮件服务未配置")
        logger.error("邮件服务未配置，已跳过通知：to=%s subject=%s", to, subject)
        return False

    message = EmailMessage()
    # 收件人/主题只来自服务端拼接的内容，用户数据一律不放进邮件头。
    message["Subject"] = subject
    message["From"] = formataddr((settings.email_from_name, settings.email_from_address))
    message["To"] = to
    message.set_content(text)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        await run_in_threadpool(_smtp_send, message)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as error:
        logger.warning("邮件发送失败 to=%s subject=%s：%s", to, subject, error)
        if required:
            raise EmailDeliveryError(str(error)) from error
        return False
    return True


# ---- 模板 ----


def _html_layout(title: str, lines: list[str], link: str | None = None, button: str = "打开链接") -> str:
    body = "".join(
        f'<p style="margin:0 0 12px">{html.escape(line)}</p>' for line in lines
    )
    action = ""
    if link:
        action = (
            f'<p style="margin:20px 0"><a href="{html.escape(link, quote=True)}"'
            ' style="display:inline-block;padding:10px 18px;background:#2f6f4f;color:#ffffff;'
            f'border-radius:6px;text-decoration:none">{html.escape(button)}</a></p>'
            f'<p style="margin:0 0 12px;color:#666;font-size:12px;word-break:break-all">{html.escape(link)}</p>'
        )
    return (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;'
        'font-size:15px;line-height:1.75;color:#222222">'
        f'<h2 style="margin:0 0 16px;font-size:18px">{html.escape(title)}</h2>'
        f"{body}{action}"
        f'<p style="margin:24px 0 0;color:#888888;font-size:12px">'
        f"本邮件由 {html.escape(BRAND)} 自动发送，请勿直接回复。</p>"
        "</div>"
    )


def _text_body(lines: list[str], link: str | None = None) -> str:
    body = "\n".join(lines)
    if link:
        body += f"\n\n{link}"
    return f"{body}\n\n—— {BRAND}（本邮件自动发送，请勿直接回复）"


def verification_message(link: str, *, ttl_hours: int) -> tuple[str, str, str]:
    lines = [
        "你好，欢迎加入万事屋。",
        f"请点击下面的链接完成邮箱验证，链接 {ttl_hours} 小时内有效：",
        "如果这不是你本人的操作，忽略本邮件即可。",
    ]
    return (
        f"【{BRAND}】验证你的邮箱",
        _text_body(lines, link),
        _html_layout("验证你的邮箱", lines, link, "完成验证"),
    )


def change_email_message(link: str, new_email: str, *, ttl_hours: int) -> tuple[str, str, str]:
    lines = [
        f"有人申请把万事屋账号的邮箱改为 {new_email}。",
        f"点击下面的链接确认变更，链接 {ttl_hours} 小时内有效：",
        "如果这不是你本人的操作，请忽略本邮件，账号号码不会被修改。",
    ]
    return (
        f"【{BRAND}】确认更换邮箱",
        _text_body(lines, link),
        _html_layout("确认更换邮箱", lines, link, "确认变更"),
    )


def email_changed_notice(old_email: str, new_email: str) -> tuple[str, str, str]:
    lines = [
        f"你的万事屋账号邮箱已从 {old_email} 变更为 {new_email}。",
        "如果这不是你本人的操作，请立即用当前密码登录并修改密码。",
    ]
    return (
        f"【{BRAND}】邮箱已变更",
        _text_body(lines),
        _html_layout("邮箱已变更", lines),
    )


def new_email_pending_notice(new_email: str) -> tuple[str, str, str]:
    lines = [
        f"你的万事屋账号正在申请把邮箱更换为 {new_email}。",
        "变更会在新邮箱点击确认链接后生效；在确认之前，当前邮箱依然有效。",
        "如果这不是你本人的操作，请立即修改密码。",
    ]
    return (
        f"【{BRAND}】有人申请更换你的邮箱",
        _text_body(lines),
        _html_layout("有人申请更换你的邮箱", lines),
    )


def reset_password_message(link: str, *, ttl_minutes: int) -> tuple[str, str, str]:
    lines = [
        "我们收到了重置万事屋账号密码的请求。",
        f"点击下面的链接设置新密码，链接 {ttl_minutes} 分钟内有效，且只能使用一次：",
        "如果这不是你本人的操作，请忽略本邮件，密码不会被修改。",
    ]
    return (
        f"【{BRAND}】重置密码",
        _text_body(lines, link),
        _html_layout("重置密码", lines, link, "设置新密码"),
    )


def password_changed_notice() -> tuple[str, str, str]:
    lines = [
        "你的万事屋账号密码刚刚被修改，此前登录的所有设备都已退出登录。",
        "如果这不是你本人的操作，请立刻使用「忘记密码」重新设置并检查账号安全。",
    ]
    return (
        f"【{BRAND}】密码已修改",
        _text_body(lines),
        _html_layout("密码已修改", lines),
    )


def login_code_message(code: str, *, ttl_minutes: int) -> tuple[str, str, str]:
    lines = [
        "你正在登录万事屋，本次登录的邮箱验证码是：",
        f"    {code}",
        f"验证码 {ttl_minutes} 分钟内有效，连续输错 5 次会作废。",
        "如果这不是你本人的操作，请立即修改密码。",
    ]
    return (
        f"【{BRAND}】登录验证码 {code}",
        _text_body(lines),
        _html_layout("登录验证码", lines),
    )


def notification_message(title: str, lines: list[str], link: str | None = None) -> tuple[str, str, str]:
    """事件通知（委托进度、审核结果等）：正文只传标题与状态，不放联系方式。"""
    return (
        f"【{BRAND}】{title}",
        _text_body(lines, link),
        _html_layout(title, lines, link, "查看详情"),
    )
