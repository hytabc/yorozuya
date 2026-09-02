from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "万事屋委托站"
    database_url: str = "sqlite:///./data/wsw.db"
    secret_key: str = "change-this-secret-in-production"
    access_token_minutes: int = 60 * 24 * 7
    # 每次数据库写入后自动快照，保留的最近备份份数
    db_backup_keep: int = 100
    admin_username: str = "admin"
    admin_password: str = "Admin123!"
    admin_nickname: str = "万事屋管理员"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def ensure_sqlite_directory(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()

