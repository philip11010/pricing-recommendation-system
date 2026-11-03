"""
Alembic environment.

The URL comes from :func:`src.db.session.database_url`, not from alembic.ini,
so the migrations and the application cannot be pointed at different
databases, and no connection string is committed.

Importing :mod:`src.db` registers every table on one metadata, so autogenerate
sees the whole schema. ``render_as_batch`` is on because SQLite cannot alter a
column in place; it is a no-op on PostgreSQL, which is the deployment target.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from src.db import Base, create_db_engine, database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it, for review or hand-off."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against the configured database."""
    engine = create_db_engine(database_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
            poolclass=pool.NullPool,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
