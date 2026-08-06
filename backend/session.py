"""SQLAlchemy engine, session factory and FastAPI dependency."""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings


def create_db_engine(database_url: str | None = None) -> Engine:
    """Build a SQLAlchemy engine from settings or an explicit URL."""
    settings = get_settings()
    url = database_url or settings.DATABASE_URL
    connect_args: dict[str, object] = {}

    is_sqlite = url.startswith("sqlite")
    is_postgres = url.startswith("postgresql")

    engine_kwargs: dict[str, object] = {"echo": False}

    if is_sqlite:
        connect_args["check_same_thread"] = False
        engine_kwargs["connect_args"] = connect_args
        engine_kwargs["pool_pre_ping"] = True
    elif is_postgres:
        engine_kwargs["connect_args"] = connect_args
        engine_kwargs["pool_size"] = settings.POOL_SIZE
        engine_kwargs["max_overflow"] = settings.MAX_OVERFLOW
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_recycle"] = 1800
    else:
        engine_kwargs["connect_args"] = connect_args
        engine_kwargs["pool_pre_ping"] = True

    engine = create_engine(url, **engine_kwargs)

    if is_sqlite:
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
