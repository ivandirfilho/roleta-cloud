"""Alembic environment para Roleta Cloud PG stack.

DSN lida de env var ROLETA_PG_DSN. Default tenta localhost dev.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DSN = os.environ.get(
    "ROLETA_PG_DSN",
    "postgresql://roleta:roleta@127.0.0.1:5432/roleta",
)
config.set_main_option("sqlalchemy.url", DSN)

target_metadata = None  # schemas geridos a mão; Alembic sem autogenerate por ora.


def run_migrations_offline() -> None:
    context.configure(
        url=DSN,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = DSN
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
