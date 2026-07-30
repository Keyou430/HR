"""SQLAlchemy engine, session factory and FastAPI dependency."""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings


def create_db_engine(database_url: str | None = None) -> Engine:
    """Build a SQLAlchemy engine from settings or an explicit URL."""
    url = database_url or get_settings().DATABASE_URL
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        url,
        echo=False,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    if url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001, ANN202
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_engine_url: str | None = None


def get_engine() -> Engine:
    """Return the module-level SQLAlchemy engine, recreating it if settings change."""
    global _engine, _engine_url, _SessionLocal
    desired_url = get_settings().DATABASE_URL
    if _engine is None or _engine_url != desired_url:
        if _engine is not None:
            _engine.dispose()
        _engine = create_db_engine(desired_url)
        _engine_url = desired_url
        _SessionLocal = None
    return _engine


def get_session_local() -> sessionmaker[Session]:
    """Return the module-level session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a per-request database session for FastAPI dependencies."""
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()
