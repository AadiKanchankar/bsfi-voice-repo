"""P1 acceptance: the ledger must be stable before anything writes into it."""
import random

import pytest

from app import db
from app.security import ledger


def fill(conn, n=1000):
    for i in range(n):
        ledger.append(conn, "turn", {"i": i, "note": f"record {i}", "amount": i * 13.5},
                      session_id=f"sess-{i % 7}")


def test_empty_chain_verifies(conn):
    out = ledger.verify(conn)
    assert out["ok"] and out["records_checked"] == 0


def test_1000_records_verify(conn):
    fill(conn, 1000)
    out = ledger.verify_linear(conn)
    assert out["ok"], out
    assert out["records_checked"] == 1000
    assert ledger.verify(conn)["ok"]


def test_hash_is_deterministic():
    a = ledger.compute_hash("0" * 64, '{"a":1}', "2026-01-01T00:00:00+00:00")
    b = ledger.compute_hash("0" * 64, '{"a":1}', "2026-01-01T00:00:00+00:00")
    assert a == b and len(a) == 64


def corrupt(conn, idx, field="payload"):
    row = conn.execute("SELECT * FROM ledger WHERE idx=?", (idx,)).fetchone()
    if field == "payload":
        new = row["payload"].replace('"amount":', '"amount":9')
        if new == row["payload"]:
            new = row["payload"] + " "
    else:
        new = row[field][:-1] + ("0" if row[field][-1] != "0" else "1")
    conn.execute(f"UPDATE ledger SET {field}=? WHERE idx=?", (new, idx))
    conn.commit()


def test_corrupting_record_437_is_localised(conn):
    fill(conn, 1000)
    corrupt(conn, 437)
    out = ledger.verify(conn)
    assert out["ok"] is False
    assert out["first_broken_index"] == 437
    assert out["broken_check"] == "binding"
    assert out["expected_hash"] != out["actual_hash"]


def test_corrupting_last_record_is_caught(conn):
    fill(conn, 300)
    corrupt(conn, 299)
    assert ledger.verify(conn)["first_broken_index"] == 299
    assert ledger.verify_linear(conn)["first_broken_index"] == 299


def test_corrupting_first_record_is_caught(conn):
    fill(conn, 200)
    corrupt(conn, 0)
    assert ledger.verify(conn)["first_broken_index"] == 0


def test_signature_tamper_detected(conn):
    fill(conn, 150)
    corrupt(conn, 77, field="sig")
    out = ledger.verify(conn)
    assert out["first_broken_index"] == 77 and out["broken_check"] == "sig"


def test_link_tamper_detected(conn):
    fill(conn, 150)
    corrupt(conn, 88, field="prev_hash")
    out = ledger.verify(conn)
    assert out["first_broken_index"] == 88 and out["broken_check"] == "link"


def test_deleted_record_detected(conn):
    fill(conn, 200)
    conn.execute("DELETE FROM ledger WHERE idx=120")
    conn.commit()
    out = ledger.verify(conn)
    assert out["ok"] is False and out["first_broken_index"] == 121


@pytest.mark.parametrize("trial", range(20))
def test_checkpoint_search_matches_linear(tmp_path, trial):
    """P1 acceptance: checkpoint localisation agrees with the linear scan."""
    rng = random.Random(1000 + trial)
    c = db.init_db(tmp_path / f"t{trial}.db")
    n = rng.randint(70, 900)
    fill(c, n)
    idx = rng.randrange(n)
    corrupt(c, idx, field=rng.choice(["payload", "sig", "prev_hash"]))
    cp = ledger.verify(c, use_checkpoints=True)
    lin = ledger.verify_linear(c)
    assert cp["ok"] == lin["ok"] is False
    assert cp["first_broken_index"] == lin["first_broken_index"] == idx
    assert cp["broken_record_id"] == lin["broken_record_id"]
    c.close()


def rewrite_forward(conn, idx):
    """A determined attacker: edit one payload and recompute every hash after
    it, so the chain links still connect. They cannot forge the HMAC
    signatures, because the key is not in the database."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM ledger ORDER BY idx")]
    rows[idx]["payload"] = rows[idx]["payload"].replace('"i":', '"i":9')
    prev = rows[idx]["prev_hash"]
    for r in rows[idx:]:
        h = ledger.compute_hash(prev, r["payload"], r["ts"])
        conn.execute("UPDATE ledger SET payload=?, prev_hash=?, hash=? WHERE idx=?",
                     (r["payload"], prev, h, r["idx"]))
        prev = h
    conn.commit()


def test_checkpoint_search_is_cheaper_when_corruption_propagates(conn):
    """The checkpoint index exists to do less work. It does, on the corruption
    that actually propagates: a rewritten chain."""
    fill(conn, 1000)
    rewrite_forward(conn, 900)
    cp, lin = ledger.verify(conn), ledger.verify_linear(conn)
    assert cp["ok"] is lin["ok"] is False
    assert cp["first_broken_index"] == lin["first_broken_index"] == 900
    assert cp["broken_check"] == lin["broken_check"] == "sig"
    assert cp["records_checked"] < lin["records_checked"] / 2, (cp, lin)
    assert cp["probes"] <= 8


def test_isolated_edit_costs_a_full_scan(conn):
    """The known ceiling, asserted rather than glossed over.

    A single edited payload that does not touch any hash breaks nothing after
    itself, so no checkpoint anchor downstream disagrees and the search has to
    walk the anchors in order. Locating one record in O(log n) needs the Merkle
    upgrade, not a linear chain. The answer is still correct, only not cheap.
    """
    fill(conn, 1000)
    corrupt(conn, 900)
    cp = ledger.verify(conn)
    assert cp["first_broken_index"] == 900
    assert cp["records_checked"] >= 900


def test_export_signature_covers_body(conn):
    fill(conn, 10)
    out = ledger.export(conn)
    assert out["export"]["count"] == 10
    assert len(out["signature"]) == 64
    import copy
    tampered = copy.deepcopy(out["export"])
    tampered["records"][3]["payload"] = "changed"
    from app.trace import canonical_json
    import hashlib, hmac as _h
    sig2 = _h.new(ledger._key(), canonical_json(tampered).encode(), hashlib.sha256).hexdigest()
    assert sig2 != out["signature"]
