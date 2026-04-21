from pathlib import Path

from app.core.config import Settings


def sqlite_file_path(database_url: str) -> Path | None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None

    raw_path = database_url.removeprefix(prefix)
    if raw_path == ":memory:":
        return None
    return Path(raw_path)


def ensure_runtime_directories(settings: Settings) -> None:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.export_dir.mkdir(parents=True, exist_ok=True)

    database_path = sqlite_file_path(settings.database_url)
    if database_path is not None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
