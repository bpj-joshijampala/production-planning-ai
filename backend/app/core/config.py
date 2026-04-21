from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Machine Shop Planning Software"
    app_version: str = "0.1.0"
    app_env: str = Field(default="local", validation_alias="APP_ENV")
    database_url: str = Field(default="sqlite:///./data/app.sqlite3", validation_alias="DATABASE_URL")
    upload_dir: Path = Field(default=Path("./data/uploads"), validation_alias="UPLOAD_DIR")
    export_dir: Path = Field(default=Path("./data/exports"), validation_alias="EXPORT_DIR")
    secret_key: str = Field(default="dev-secret-change-me", validation_alias="SECRET_KEY")
    max_upload_size_mb: int = Field(default=25, validation_alias="MAX_UPLOAD_SIZE_MB")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
