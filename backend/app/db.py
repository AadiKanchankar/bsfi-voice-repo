"""Database access.

Two doors onto one SQLite file, deliberately:

- `connect()` returns a plain `sqlite3.Connection`. Most of the pipeline uses
  it, and demo beat 10 depends on it: a presenter edits a stored row with raw
  SQL and the hash chain catches it. An ORM in the middle of that would be a
  layer to explain with nothing to show.
- `engine()` and `session()` are SQLModel, used by the newer tables (calls,
  recordings, cases, access log) where relationships and typed rows earn
  their keep.

The SCHEMA is no longer written here. `app/models.py` declares it and Alembic
migrates it, so the shape of the database is versioned and a PostgreSQL swap
is a URL change. `init_db()` runs any pending migration on startup, which
means a developer who pulls a schema change does not have to remember to.
See DECISIONS.md D20.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH, RUNTIME_DIR, VAULT_DIR, db_url

# Pragmas applied to every raw connection. synchronous=NORMAL is the
# documented safe pairing with WAL: commits stop fsyncing, which on this
# hardware is the difference between 0.4 s and 0.02 ms per ledger append. A
# power loss can lose the last few commits but cannot corrupt the chain.
PRAGMAS = ("PRAGMA journal_mode=WAL",
           "PRAGMA synchronous=NORMAL",
           "PRAGMA foreign_keys=ON",
           "PRAGMA busy_timeout=5000")

_migrated: set[str] = set()
_migrate_lock = threading.Lock()


def _alembic_config(url: str):
    from alembic.config import Config
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def migrate(url: str | None = None) -> None:
    """Bring the database up to head. Idempotent, and run once per URL per
    process so a test suite that opens fifty databases is not fifty upgrades
    of the same one."""
    import logging
    from alembic import command
    target = url or db_url()
    with _migrate_lock:
        if target in _migrated:
            return
        # Alembic logs three INFO lines per upgrade. On a test suite that
        # creates a database per test that is noise, not information.
        # alembic.runtime.migration is the logger that actually emits the
        # three INFO lines, and alembic.ini's fileConfig sets its level, so
        # quieting the parent is not enough.
        noisy = [logging.getLogger(n) for n in
                 ("alembic", "alembic.runtime.migration", "alembic.env")]
        levels = [lg.level for lg in noisy]
        for lg in noisy:
            lg.setLevel(logging.WARNING)
        try:
            command.upgrade(_alembic_config(target), "head")
        finally:
            for lg, lv in zip(noisy, levels):
                lg.setLevel(lv)
        _migrated.add(target)



def connect(path: Path | None = None) -> sqlite3.Connection:
    """A raw connection with the pragmas applied."""
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    for pragma in PRAGMAS:
        conn.execute(pragma)
    return conn


def init_db(path: Path | None = None) -> sqlite3.Connection:
    """Migrate to head, then hand back a raw connection.

    Tests pass an explicit path and get their own migrated database.
    """
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    target = f"sqlite:///{Path(path).resolve()}" if path else db_url()
    migrate(target)
    return connect(path)


@contextmanager
def tx(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------- SQLModel

_engines: dict[str, object] = {}


def engine(url: str | None = None):
    """A SQLModel engine, one per URL, migrated on first use."""
    from sqlalchemy import event
    from sqlmodel import create_engine
    target = url or db_url()
    if target not in _engines:
        migrate(target)
        eng = create_engine(target, echo=False,
                            connect_args={"check_same_thread": False}
                            if target.startswith("sqlite") else {})
        if target.startswith("sqlite"):
            @event.listens_for(eng, "connect")
            def _pragmas(dbapi_conn, _record):      # noqa: ANN001
                cur = dbapi_conn.cursor()
                for pragma in PRAGMAS:
                    cur.execute(pragma)
                cur.close()
        _engines[target] = eng
    return _engines[target]


@contextmanager
def session(url: str | None = None):
    """A SQLModel session that commits on success and rolls back on error."""
    from sqlmodel import Session
    with Session(engine(url)) as s:
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
