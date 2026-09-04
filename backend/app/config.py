from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "万事屋委托站"
    database_url: str = "sqlite:///./data/wsw.db"
    secret_key: str = "change-this-secret-in-production"
    # 登录会话最多持续 24 小时，超时后必须重新验证密码。
    access_token_minutes: int = 60 * 24
    # 每次数据库写入后自动快照，保留的最近备份份数
    db_backup_keep: int = 100
    admin_username: str = "admin"
    admin_password: str = "Admin123!"
    admin_nickname: str = "万事屋管理员"
    staff_group_id: str = ""
    # 留空时跟随 SQLite 数据库所在目录，保证数据库与上传图片能一起通过 Docker 挂载持久化。
    sugar_upload_dir: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # 万事屋看板娘(站内 AI 助手):不填 MASCOT_API_KEY 则聊天接口优雅降级为“未启用”
    mascot_api_base: str = "https://api.moonshot.cn/v1"
    mascot_api_key: str = ""
    mascot_model: str = "kimi-k2.7-code-highspeed"
    mascot_max_tokens: int = 1500
    mascot_timeout_seconds: int = 120

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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


settings = Settings()
