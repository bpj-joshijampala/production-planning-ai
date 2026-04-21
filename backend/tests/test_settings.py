from pathlib import Path

from app.core.config import Settings
from app.core.paths import sqlite_file_path


def test_settings_have_m0_defaults() -> None:
    settings = Settings()

    assert settings.app_env == "local"
    assert settings.database_url == "sqlite:///./data/app.sqlite3"
    assert settings.upload_dir == Path("data/uploads")
    assert settings.export_dir == Path("data/exports")
    assert settings.max_upload_size_mb == 25
    assert settings.log_level == "INFO"


def test_settings_read_environment_variables(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./tmp/test.sqlite3")
    monkeypatch.setenv("UPLOAD_DIR", "./tmp/uploads")
    monkeypatch.setenv("EXPORT_DIR", "./tmp/exports")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "10")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings()

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite:///./tmp/test.sqlite3"
    assert settings.upload_dir == Path("tmp/uploads")
    assert settings.export_dir == Path("tmp/exports")
    assert settings.secret_key == "test-secret"
    assert settings.max_upload_size_mb == 10
    assert settings.log_level == "DEBUG"


def test_sqlite_file_path_extracts_local_database_path() -> None:
    assert sqlite_file_path("sqlite:///./data/app.sqlite3") == Path("data/app.sqlite3")
    assert sqlite_file_path("sqlite:///:memory:") is None
    assert sqlite_file_path("postgresql://example") is None
