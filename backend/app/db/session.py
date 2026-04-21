from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def create_db_engine(settings: Settings | None = None) -> Engine:
    resolved_settings = settings or get_settings()
    connect_args = {}
    if _is_sqlite_url(resolved_settings.database_url):
        connect_args["check_same_thread"] = False

    engine = create_engine(resolved_settings.database_url, connect_args=connect_args)

    if _is_sqlite_url(resolved_settings.database_url):
        _apply_sqlite_pragmas(engine)

    return engine


def _apply_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def create_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_db_engine(settings), autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = create_session_factory()()
    try:
        yield db
    finally:
        db.close()
