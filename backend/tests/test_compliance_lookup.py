"""R2. The compliance lookup, and the record of it being used.

The defect this covers is in DECISIONS.md D22: the old lookup answered
`200 {"traces": []}` for an unknown id, a partial id, a customer id and a
typo alike, so nothing a user typed could report failure and the dashboard
just stayed blank.

Every test here asserts one of the three rules that replaced it: a miss is a
miss, a leading fragment of an id is enough, and looking is itself an event.
"""
import pytest
from fastapi.testclient import TestClient

from app import compliance, db, main, turn
from app.banking import registry
from app.security import ledger


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(main, "METRICS", {"turns": 0, "decisions": {}, "stage_ms": {},
                                          "errors": 0})
    with TestClient(main.app) as c:
        yield c


def token(client, role):
    r = client.post("/auth/demo-token", json={"subject": f"demo-{role}", "role": role})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def seed_call(conn, *, mobile="9822012345", name="Lookup Target"):
    cust = registry.create_customer(conn, name=name, mobile=mobile)
    s = turn.create_session(conn, cust["customer_id"])
    conn.execute(
        "INSERT INTO turns (call_id, turn_id, trace_id, decision, risk_tier,"
        " language, interrupted, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (s["call_id"], 0, "trace-0", "refused", 3, "hi", 0, "2026-09-21T10:00:00+00:00"))
    conn.commit()
    return cust, s


# ---------------------------------------------------------------- resolve

def test_a_miss_is_a_miss_not_an_empty_result(conn):
    assert compliance.resolve(conn, "nonsense-id") is None
    assert compliance.resolve(conn, "") is None
    assert compliance.resolve(conn, "   ") is None


def test_a_leading_fragment_of_an_id_is_enough(conn):
    """The console only ever shows eight characters of a session id."""
    cust, s = seed_call(conn)
    hit = compliance.resolve(conn, s["session_id"][:8])
    assert hit == {"kind": "session", "id": s["session_id"], "call_id": s["call_id"]}
    assert compliance.resolve(conn, s["call_id"][:8])["kind"] == "call"
    assert compliance.resolve(conn, cust["customer_id"][:6])["kind"] == "customer"


def test_a_stated_mobile_resolves_to_its_customer(conn):
    cust, _ = seed_call(conn, mobile="9822077777")
    assert compliance.resolve(conn, "9822077777") == {"kind": "customer",
                                                      "id": cust["customer_id"]}


def test_an_ambiguous_mobile_resolves_to_nobody(conn):
    seed_call(conn, mobile="9822012345", name="A")
    registry.create_customer(conn, name="B", mobile="9111112345")
    assert compliance.resolve(conn, "9822012345") is None


# ---------------------------------------------------------------- filters

def test_filters_select_on_the_turns_of_a_call(conn):
    """A call is interesting because one turn in it was refused, not because
    its last turn was."""
    _, s = seed_call(conn)
    assert len(compliance.search_calls(conn, decision="refused")) == 1
    assert compliance.search_calls(conn, decision="automated") == []
    assert len(compliance.search_calls(conn, tier=3)) == 1
    assert compliance.search_calls(conn, tier=4) == []
    assert len(compliance.search_calls(conn, language="hi")) == 1
    assert compliance.search_calls(conn, language="mr") == []
    assert compliance.search_calls(conn, date_from="2099-01-01") == []


def test_a_call_summary_carries_what_the_list_shows(conn):
    cust, s = seed_call(conn)
    row = compliance.search_calls(conn, customer_id=cust["customer_id"])[0]
    assert row["call_id"] == s["call_id"]
    assert row["customer_name"] == "Lookup Target"
    assert row["turns"] == 1 and row["max_tier"] == 3
    assert row["recordings"] == 0 and row["cases"] == 0


# ---------------------------------------------------------------- drill-down

def test_call_detail_is_none_for_an_unknown_call(conn):
    assert compliance.call_detail(conn, "CALLNOPE") is None


def test_call_detail_carries_the_ledger_with_per_record_status(conn):
    _, s = seed_call(conn)
    out = compliance.call_detail(conn, s["call_id"])
    assert out["call"]["call_id"] == s["call_id"]
    assert [t["turn_id"] for t in out["turns"]] == [0]
    assert out["ledger"], "the consent record at least should be here"
    assert all(r["verified"] for r in out["ledger"])


def test_a_tampered_record_shows_as_broken_in_the_drill_down(conn):
    """Beat 10, scoped to one call. A plain SQL edit, nothing else."""
    _, s = seed_call(conn)
    idx = conn.execute("SELECT idx FROM ledger WHERE session_id=? ORDER BY idx",
                       (s["session_id"],)).fetchone()["idx"]
    conn.execute("UPDATE ledger SET payload=? WHERE idx=?",
                 ('{"tampered":true}', idx))
    conn.commit()
    out = compliance.call_detail(conn, s["call_id"])
    broken = [r for r in out["ledger"] if not r["verified"]]
    assert [r["idx"] for r in broken] == [idx]
    assert broken[0]["reason"] == "binding"
    assert ledger.verify_record(conn, idx)["ok"] is False


# ---------------------------------------------------------------- audit

def test_every_look_is_written_to_the_access_log_and_the_ledger(conn):
    _, s = seed_call(conn)
    before = conn.execute("SELECT COUNT(*) c FROM access_log").fetchone()["c"]
    compliance.record_access(conn, actor="officer-1", role="compliance_officer",
                             action="search", target_type="call",
                             target_id=s["call_id"], hits=1)
    after = conn.execute("SELECT COUNT(*) c FROM access_log").fetchone()["c"]
    assert after == before + 1
    kinds = [r["kind"] for r in conn.execute("SELECT kind FROM ledger")]
    assert "compliance_access" in kinds


# ---------------------------------------------------------------- over HTTP

def test_the_search_endpoint_404s_with_a_message_that_says_what_to_type(client):
    r = client.get("/search?q=nonsense-id", headers=token(client, "compliance_officer"))
    assert r.status_code == 404
    detail = r.json()["detail"]
    for word in ("call id", "session id", "customer id", "case id"):
        assert word in detail
    assert "leading part" in detail


def test_the_search_endpoint_finds_a_call_by_a_partial_id(client):
    reg = client.post("/customers", json={"name": "HTTP Target", "mobile": "9822033333"},
                      headers=token(client, "customer")).json()
    s = client.post("/session/consent", json={"customer_id": reg["customer_id"],
                                              "accepted": True},
                    headers=token(client, "customer")).json()
    hdr = token(client, "compliance_officer")

    r = client.get(f"/search?q={s['call_id'][:8]}", headers=hdr)
    assert r.status_code == 200 and r.json() == {"kind": "call", "id": s["call_id"]}

    r = client.get(f"/calls/{s['call_id']}", headers=hdr)
    assert r.status_code == 200
    assert r.json()["call"]["customer_id"] == reg["customer_id"]

    assert client.get("/calls/CALLNOPE", headers=hdr).status_code == 404
    assert client.get("/customers/CUSTNOPE", headers=hdr).status_code == 404


def test_a_customer_token_cannot_reach_any_of_the_lookup(client):
    for role in ("customer", "agent"):
        hdr = token(client, role)
        for path in ("/search?q=x", "/calls", "/calls/CALL1", "/customers/CUST1000",
                     "/customers/CUST1000/calls", "/cases", "/access-log"):
            assert client.get(path, headers=hdr).status_code == 403, path


def test_searching_over_http_lands_in_the_access_log(client):
    hdr = token(client, "compliance_officer")
    client.get("/search?q=nothing-here", headers=hdr)
    client.get("/calls", headers=hdr)
    entries = client.get("/access-log", headers=hdr).json()["entries"]
    actions = {e["action"] for e in entries}
    assert {"search", "search_calls"} <= actions
    assert any(e["actor"] == "demo-compliance_officer" for e in entries)


def test_interrupted_calls_can_be_found(conn):
    """The change request lists `interrupted` beside the decisions, because
    an officer asking "which calls did we talk over" is asking the same kind
    of question."""
    from app import call as callsm
    cust, s = seed_call(conn)
    conn.execute("UPDATE turns SET interrupted=1 WHERE call_id=?", (s["call_id"],))
    conn.commit()

    found = compliance.search_calls(conn, decision="interrupted")
    assert [r["call_id"] for r in found] == [s["call_id"]]
    assert found[0]["interrupted"] == 1

    # And a call with nothing interrupted does not match.
    other = turn.create_session(conn, cust["customer_id"])
    conn.execute("INSERT INTO turns (call_id, turn_id, decision, interrupted,"
                 " created_at) VALUES (?,?,?,?,?)",
                 (other["call_id"], 0, "automated", 0, "2026-09-21T11:00:00+00:00"))
    conn.commit()
    assert other["call_id"] not in [
        r["call_id"] for r in compliance.search_calls(conn, decision="interrupted")]
