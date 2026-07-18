"""
Alembic migration environment.
Supports both offline (SQL script) and online (live DB) modes.
Uses the sync DATABASE_URL_SYNC DSN since Alembic doesn't support async natively.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Pull the sync DSN from environment (overrides alembic.ini) ──────────────
from dotenv import load_dotenv

load_dotenv()

# ── Import Base with all models registered ───────────────────────────────────
from app.db.base import Base  # noqa: E402

config = context.config

# Override sqlalchemy.url with env var if available
sync_url = os.getenv("DATABASE_URL_SYNC")
if sync_url:
    config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL script without a live DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
