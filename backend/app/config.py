import logging
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("yorozuya.config")

# 代码内置的占位值：一旦生效，JWT 可被伪造 / 管理员密码人人皆知，必须替换。
INSECURE_DEFAULT_SECRET = "change-this-secret-in-production"
INSECURE_DEFAULT_ADMIN_PASSWORD = "Admin123!"


class Settings(BaseSettings):
    app_name: str = "万事屋委托站"
    database_url: str = "sqlite:///./data/wsw.db"
    secret_key: str = INSECURE_DEFAULT_SECRET
    # 登录会话最多持续 24 小时，超时后必须重新验证密码。
    access_token_minutes: int = 60 * 24
    # “自动登录”令牌有效期（天）。硬上限 7 天，配置更大也不会超过。
    remember_token_days: int = 7
    # 每次数据库写入后自动快照，保留的最近备份份数
    db_backup_keep: int = 100
    admin_username: str = "admin"
    admin_password: str = INSECURE_DEFAULT_ADMIN_PASSWORD
    admin_nickname: str = "万事屋管理员"
    # 留空时跟随 SQLite 数据库所在目录，保证数据库与上传图片能一起通过 Docker 挂载持久化。
    # 该目录是「公开区」：只有已过审的媒体才会放在这里，由 /uploads 静态托管。
    sugar_upload_dir: str = ""
    # 待审/被屏蔽的媒体存放在这里（「私有区」）：不在任何静态挂载范围内，
    # 只能凭 /api/media/{key}?exp=&sig= 的短时签名访问。留空时取上传目录同级的 private_media。
    media_private_dir: str = ""
    # 私有媒体签名 URL 的有效期（秒）。每次接口响应都会重新签发，因此可以设得较短：
    # 越短则「审核驳回后旧链接失效」越快，过长会削弱撤回效果。
    media_token_ttl_seconds: int = 6 * 60 * 60
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    # 反向代理后部署时（Docker/HTTPS 入口）设为 True，限流按真实客户端 IP 统计。
    behind_proxy: bool = False

    # 万事屋看板娘(站内 AI 助手):不填 MASCOT_API_KEY 则聊天接口优雅降级为“未启用”
    mascot_api_base: str = "https://api.moonshot.cn/v1"
    mascot_api_key: str = ""
    mascot_model: str = "kimi-k2.7-code-highspeed"
    mascot_max_tokens: int = 1500
    mascot_timeout_seconds: int = 120

    # 登录/注册人机验证：turnstile=Cloudflare Turnstile；builtin=站内图形验证码。
    # 关闭 CAPTCHA_ENABLED 则登录/注册不再要求验证码（不推荐生产环境关闭）。
    captcha_enabled: bool = True
    captcha_provider: str = "turnstile"
    # builtin 验证码有效期（秒）
    captcha_ttl_seconds: int = 180
    # Turnstile 公开 Site Key 可入库；Secret Key 只能放服务端 .env。
    turnstile_site_key: str = "0x4AAAAAAEwPP7x-AwVA_SVE"
    turnstile_secret_key: str = ""

    # 网站备案号（页脚展示）。属于私有信息，只从 .env 读取，留空则页脚不展示。
    site_icp: str = ""
    # 备案号点击后跳转的官方查询地址（工信部备案系统，公开地址）。
    site_icp_url: str = "https://beian.miit.gov.cn/"

    # ── 邮箱验证与邮件通知（SMTP，示例为阿里云邮件推送 DirectMail）──
    # smtp=真实发信；log=只打印到日志并写入 mailer.OUTBOX（本地开发与测试用）。
    email_delivery: str = "smtp"
    smtp_host: str = "smtpdm.aliyun.com"
    smtp_port: int = 465
    # 连接加密方式：ssl=直接 TLS（465，阿里云/163/QQ 推荐）；starttls=先明文再升级（80/25）；none=不加密。
    smtp_encryption: str = "ssl"
    smtp_timeout_seconds: int = 15
    smtp_username: str = ""
    # ⚠️ 服务商后台的「SMTP 密码」（阿里云邮件推送在发信地址处设置），只放 .env，绝不写进任何入库文件。
    smtp_password: str = ""
    # ⚠️ 必须是服务商后台已验证的发信地址（阿里云：发信域名需验证、发信地址需在控制台创建）。
    email_from_address: str = ""
    email_from_name: str = "万事屋委托站"
    # 邮件里链接的前缀，例如 https://example.com；留空则按请求的 Host 推导。
    site_base_url: str = ""
    # 邮箱验证链接有效期（小时）。
    email_verification_ttl_hours: int = 24
    # 重置密码链接有效期（分钟）。
    password_reset_ttl_minutes: int = 30
    # 登录邮箱验证码有效期（分钟）。
    login_code_ttl_minutes: int = 10
    # 同一账号同一用途两次发信的最小间隔（秒），防止连点把邮箱刷爆；0 表示不限制。
    email_send_cooldown_seconds: int = 60
    # 登录时是否要求邮箱验证码（二次验证）。邮箱服务不可用时建议临时关闭。
    login_code_required: bool = True
    # 未验证邮箱是否封锁写操作。
    # ⚠️ 救援开关：邮件配置出错导致无人能验证时，置 false 重启即可恢复使用。
    require_email_verification: bool = True
    # 事件通知邮件总开关。
    notify_email_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def model_post_init(self, __context) -> None:
        # 未配置 SECRET_KEY 时绝不能使用公开的占位值签名令牌：
        # 改用本次进程的随机会话密钥（重启后旧登录失效，但令牌无法被伪造）。
        if not self.secret_key or self.secret_key == INSECURE_DEFAULT_SECRET:
            self.secret_key = secrets.token_urlsafe(48)
            logger.warning(
                "未检测到有效的 SECRET_KEY，已为本次运行生成临时密钥。"
                "所有登录会在重启后失效，请在 .env 中设置固定的 SECRET_KEY（openssl rand -hex 32）。"
            )
        # 接口允许携带凭证（Authorization / 未来可能的 Cookie），通配来源等于让任意站点
        # 带着访客的登录态调用本站接口，因此必须直接拒绝而不是静默生效。
        if "*" in self.cors_origin_list:
            raise RuntimeError(
                "CORS_ORIGINS 不能包含 *：本站接口允许携带凭证，通配来源会让任意网站"
                "以访客身份调用本站接口。请改为逐个列出真实来源，例如 https://example.com。"
            )
        if self.email_delivery not in ("smtp", "log"):
            raise RuntimeError(
                f"EMAIL_DELIVERY 只能是 smtp 或 log（当前 {self.email_delivery!r}）："
                "smtp 为真实发信，log 只把邮件打印到日志供本地开发使用。"
            )
        if self.smtp_encryption not in ("ssl", "starttls", "none"):
            raise RuntimeError(
                f"SMTP_ENCRYPTION 只能是 ssl / starttls / none（当前 {self.smtp_encryption!r}）："
                "阿里云邮件推送用 465 + ssl，也可用 80/25 + starttls。"
            )

    @property
    def admin_password_is_default(self) -> bool:
        return not self.admin_password or self.admin_password == INSECURE_DEFAULT_ADMIN_PASSWORD

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def smtp_ready(self) -> bool:
        """当前配置能否真正发信：log 模式恒可（走 OUTBOX），smtp 模式需要四项齐全。"""
        if self.email_delivery != "smtp":
            return True
        return bool(self.smtp_host and self.smtp_username and self.smtp_password and self.email_from_address)

    def validate_email_config(self) -> None:
        """启动自检：smtp 模式缺凭据时给出醒目日志。

        刻意不阻止启动：站点仍可浏览，只有依赖邮件的操作会 fail-closed 返回 503，
        这样运维仍能进站排查，而不是面对一个起不来的容器。
        """
        if self.email_delivery == "smtp" and not self.smtp_ready:
            logger.error(
                "EMAIL_DELIVERY=smtp 但邮件配置不完整（需要 SMTP_USERNAME / SMTP_PASSWORD / "
                "EMAIL_FROM_ADDRESS）：注册、邮箱验证、找回密码等操作将返回 503。"
                "本地开发可设 EMAIL_DELIVERY=log 只打印邮件不发送。"
            )
        if self.email_delivery == "smtp" and self.email_from_address and self.smtp_username:
            if self.email_from_address.lower() != self.smtp_username.lower():
                logger.info(
                    "邮件发件地址为 %s（与 SMTP 登录账号不同时，请确认它是服务商后台已验证的发信地址，"
                    "否则会被拒收 553/554）。",
                    self.email_from_address,
                )

    @property
    def safe_site_icp_url(self) -> str:
        """页脚备案链接只接受 https，避免 .env 误配成 javascript: 等伪协议后被放进 href。"""
        candidate = self.site_icp_url.strip()
        if candidate.startswith("https://"):
            return candidate
        if candidate:
            logger.warning("SITE_ICP_URL 必须是 https 地址，已回落到默认工信部备案查询地址：%s", candidate)
        return "https://beian.miit.gov.cn/"

    def _unwritable_error(self, label: str, path: Path, error: OSError) -> RuntimeError:
        """把目录不可写翻译成可执行的中文提示：裸的 PermissionError 堆栈无法指导运维。"""
        return RuntimeError(
            f"{label} {path} 不可写（{error}）。容器以非 root 用户（UID 10001）运行时，"
            "请在宿主机执行一次 chown -R 10001:10001 backend/data（即挂载到 /data 的目录）后重启。"
        )

    def ensure_sqlite_directory(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.removeprefix("sqlite:///"))
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise self._unwritable_error("数据库目录", db_path.parent, error) from error

    @property
    def sugar_upload_path(self) -> Path:
        if self.sugar_upload_dir:
            return Path(self.sugar_upload_dir)
        if self.database_url.startswith("sqlite:///"):
            database_path = Path(self.database_url.removeprefix("sqlite:///"))
            return database_path.parent / "uploads"
        return Path("./data/uploads")

    @property
    def media_private_path(self) -> Path:
        """私有媒体目录：默认与公开上传目录同级，便于随数据目录一起挂载持久化。"""
        if self.media_private_dir:
            return Path(self.media_private_dir)
        return self.sugar_upload_path.parent / "private_media"

    def ensure_storage_directory(self) -> None:
        """创建公开上传区与私有媒体目录。

        ⚠️ 本方法在导入 database.py 时就会执行，早于 main.py 的启动自检，
        因此必须自己抛出可读的中文提示；否则目录不可写时运维看到的只是 PermissionError 堆栈。
        """
        for path, label in ((self.sugar_upload_path, "上传目录"), (self.media_private_path, "私有媒体目录")):
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise self._unwritable_error(label, path, error) from error

    def validate_storage_isolation(self) -> None:
        """防止把上传目录配成数据库目录，否则 wsw.db / backups 会被静态托管下载。"""
        if not self.database_url.startswith("sqlite:///"):
            return
        db_path = Path(self.database_url.removeprefix("sqlite:///")).resolve()
        upload_path = self.sugar_upload_path.resolve()
        if db_path == upload_path or upload_path in db_path.parents:
            raise RuntimeError(
                "SUGAR_UPLOAD_DIR 不能指向数据库所在目录（或它的上级），"
                "否则数据库与备份文件会通过 /uploads 被公开下载。请改为独立的子目录，例如 <data>/uploads。"
            )
        private_path = self.media_private_path.resolve()
        if private_path == db_path or private_path in db_path.parents:
            raise RuntimeError(
                "MEDIA_PRIVATE_DIR 不能指向数据库所在目录（或它的上级），"
                "否则数据库与备份文件可能随媒体一起被读取。请改用独立的子目录，例如 <data>/private_media。"
            )
        # 私有区一旦落在公开上传目录之内，待审媒体又会通过 /uploads 直接可下载，
        # 等于整套受控访问失效，因此必须在启动时拦住。
        if private_path == upload_path or upload_path in private_path.parents:
            raise RuntimeError(
                "MEDIA_PRIVATE_DIR 不能位于 SUGAR_UPLOAD_DIR（公开上传目录）之内，"
                "否则待审/被屏蔽的图片仍会被 /uploads 公开下载。请改用与上传目录同级的独立目录。"
            )

    def validate_directories_writable(self) -> None:
        """启动自检：数据目录不可写时给出可执行的中文提示，而不是等 sqlite 抛出堆栈。"""
        targets = [(self.sugar_upload_path, "上传目录"), (self.media_private_path, "私有媒体目录")]
        if self.database_url.startswith("sqlite:///"):
            targets.append((Path(self.database_url.removeprefix("sqlite:///")).parent, "数据库目录"))
        for path, label in targets:
            try:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / ".yorozuya-write-test"
                with probe.open("wb"):
                    pass
                probe.unlink(missing_ok=True)
            except OSError as error:
                raise self._unwritable_error(label, path, error) from error


settings = Settings()
