"""Alembic environment configuration for Replica RBAC v2.0.

Uses the shared SQLAlchemy MetaData from store.py as target, and resolves
the database URL from config.Settings so tests can override it via env vars.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure backend/ is on sys.path so we can import our modules
_backend_root = Path(__file__).resolve().parents[1]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

# Alembic Config object (reads alembic.ini)
config = context.config

# Set up Python logging from the config file section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the shared MetaData — this holds ALL table definitions so
# autogenerate can detect schema differences.
from store import metadata  # noqa: E402

target_metadata = metadata

# Resolve the database URL dynamically from our settings
from config import get_settings  # noqa: E402


def get_url() -> str:
    return get_settings().DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (against a live database)."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite needs batch mode for ALTER TABLE operations
            render_as_batch=bool(get_url().startswith("sqlite")),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
