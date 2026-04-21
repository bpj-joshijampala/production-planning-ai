import sqlite3

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.session import create_db_engine


def test_sqlite_foreign_keys_are_enabled(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database_url = f"sqlite:///{tmp_path.as_posix()}/foreign_keys.sqlite3"
    engine = create_db_engine(Settings(DATABASE_URL=database_url))

    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_alembic_upgrade_creates_migration_metadata(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "migration.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
        assert "alembic_version" in tables
        assert "app_metadata" in tables

        schema_baseline = connection.execute(
            "select value from app_metadata where key = 'schema_baseline'"
        ).fetchone()
        assert schema_baseline == ("m0",)
