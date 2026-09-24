import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import pytest                                   # noqa: E402
from app import db                              # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    """An empty, migrated database. No customers, no accounts, no models."""
    c = db.init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture(scope="module")
def live():
    """A seeded database plus the real models.

    Uses the project runtime, since the intent head and the KB index are
    built by `make seed` and rebuilding them per test would make the suite
    unusable. Anything that needs a customer with accounts, payees and a
    trained intent head wants this rather than `conn`.
    """
    from app.config import DB_PATH, RUNTIME_DIR
    if not (RUNTIME_DIR / "nlu_head.pkl").exists():
        pytest.skip("run `make seed` first")
    c = db.init_db(DB_PATH)
    if not c.execute("SELECT 1 FROM customers LIMIT 1").fetchone():
        pytest.skip("no seeded customers; run `make seed`")
    yield c
    c.close()
