"""Alembic environment.

The database URL comes from the application config, not from alembic.ini, so
there is exactly one place that decides where the data lives. Swapping SQLite
for PostgreSQL is then `BFSI_DB_URL=postgresql+psycopg://...` and nothing
else: the models in app/models.py are written to be portable.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, event, pool

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import db_url                       # noqa: E402
from app import models                              # noqa: E402,F401  (registers tables)
from sqlmodel import SQLModel                       # noqa: E402

config = context.config
# Only fall back to the application default when the caller has not already
# chosen a URL. db.migrate() sets one per database, and overwriting it here
# sent every test's migration to the shared development database instead of
# the test's own file.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", db_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _common(**kw):
    return dict(
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite cannot ALTER most things in place, so Alembic rewrites the
        # table. Without this, any future column change fails on SQLite and
        # works on PostgreSQL, which is the worst kind of difference.
        render_as_batch=True,
        **kw,
    )


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, **_common())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool)
    # The pragmas go on the connect event, not on an open connection.
    #
    # Without them the migration runs in rollback-journal mode with
    # synchronous=FULL, so every CREATE TABLE waits on an fsync. On a busy
    # ext4 journal that is roughly half a second each, and this schema has two
    # dozen tables, which made a test suite that migrates a fresh database per
    # test take twenty seconds a test instead of a quarter of one.
    #
    # Setting them on an already-open connection does not work and fails in a
    # way that looks like success: SQLAlchemy has begun an implicit
    # transaction by then, `PRAGMA journal_mode` is a no-op inside one, and
    # the transaction boundary alembic then opens is no longer its own. The
    # symptom was a migration whose DDL landed while alembic_version stayed on
    # the previous revision, so the next startup tried to add the same columns
    # again and the server exited.
    @event.listens_for(connectable, "connect")
    def _pragmas(dbapi_conn, _record):          # noqa: ANN001
        if connectable.dialect.name != "sqlite":
            return
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    with connectable.connect() as connection:
        context.configure(connection=connection, **_common())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
