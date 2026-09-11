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
    # 每次数据库写入后自动快照，保留的最近备份份数
    db_backup_keep: int = 100
    admin_username: str = "admin"
    admin_password: str = INSECURE_DEFAULT_ADMIN_PASSWORD
    admin_nickname: str = "万事屋管理员"
    # 留空时跟随 SQLite 数据库所在目录，保证数据库与上传图片能一起通过 Docker 挂载持久化。
    sugar_upload_dir: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    # 反向代理后部署时（Docker/FRP）设为 True，限流按真实客户端 IP 统计。
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

    @property
    def admin_password_is_default(self) -> bool:
        return not self.admin_password or self.admin_password == INSECURE_DEFAULT_ADMIN_PASSWORD

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def ensure_sqlite_directory(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def sugar_upload_path(self) -> Path:
        if self.sugar_upload_dir:
            return Path(self.sugar_upload_dir)
        if self.database_url.startswith("sqlite:///"):
            database_path = Path(self.database_url.removeprefix("sqlite:///"))
            return database_path.parent / "uploads"
        return Path("./data/uploads")

    def ensure_storage_directory(self) -> None:
        self.sugar_upload_path.mkdir(parents=True, exist_ok=True)

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


settings = Settings()
