"""Section 8. The HTTP contract and the authorisation boundary on it.

These tests hit the real app through TestClient, so a permission that is
correct in the matrix but wired to the wrong endpoint still fails here.
"""
import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.config import ROLES


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A throwaway database per test.

    main.DB_PATH is patched rather than main.CONN, because the app lifespan
    opens the connection itself on startup and would overwrite a pre-set CONN.
    Getting this wrong means the tests quietly run against the real demo
    database, which is how the first version of this fixture passed while
    asserting nothing useful.
    """
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(main, "METRICS", {"turns": 0, "decisions": {}, "stage_ms": {},
                                          "errors": 0})
    with TestClient(main.app) as c:
        yield c


def token(client, role):
    r = client.post("/auth/demo-token", json={"subject": f"demo-{role}", "role": role})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_capabilities_is_open_and_declares_everything(client):
    r = client.get("/capabilities")
    assert r.status_code == 200
    body = r.json()
    caps = body["capabilities"]
    assert caps["antispoof"]["status"] == "BASELINE"
    assert caps["core_banking"]["status"] == "SIMULATED"
    assert caps["otp"]["status"] == "SIMULATED"
    assert caps["ledger"]["status"] == "REAL"
    assert set(body["legend"]) == {"REAL", "BASELINE", "SIMULATED"}
    assert "synthetic" in body["synthetic_data_notice"].lower()


def test_every_other_endpoint_needs_a_token(client):
    for method, path in [("post", "/session/consent"), ("post", "/turn/text"),
                         ("post", "/ledger/verify"), ("get", "/ledger/export"),
                         ("get", "/metrics"), ("get", "/handovers"), ("get", "/kb")]:
        kwargs = {"json": {}} if method == "post" else {}
        r = getattr(client, method)(path, **kwargs)
        assert r.status_code == 401, (method, path, r.status_code)


def test_customer_cannot_export_the_ledger(client):
    """The single most important cell in the role matrix."""
    r = client.get("/ledger/export", headers=token(client, "customer"))
    assert r.status_code == 403
    assert "may not" in r.json()["detail"]


def test_compliance_officer_can_export_the_ledger(client):
    r = client.get("/ledger/export", headers=token(client, "compliance_officer"))
    assert r.status_code == 200
    body = r.json()
    assert body["signature_alg"] == "HMAC-SHA256" and len(body["signature"]) == 64


def test_compliance_officer_cannot_submit_a_turn(client):
    r = client.post("/turn/text", json={"session_id": "x", "text": "hello"},
                    headers=token(client, "compliance_officer"))
    assert r.status_code == 403


def test_customer_cannot_claim_a_handover(client):
    r = client.post("/agent/handover/does-not-matter", headers=token(client, "customer"))
    assert r.status_code == 403


def test_bad_token_is_rejected(client):
    r = client.post("/ledger/verify", headers={"Authorization": "Bearer nonsense"})
    assert r.status_code == 401


def test_unknown_role_is_refused_by_the_issuer(client):
    r = client.post("/auth/demo-token", json={"subject": "x", "role": "superuser"})
    assert r.status_code == 400


def test_consent_required_to_open_a_session(client):
    r = client.post("/session/consent", json={"accepted": False},
                    headers=token(client, "customer"))
    assert r.status_code == 400


def test_session_consent_writes_the_first_ledger_record(client):
    r = client.post("/session/consent", json={"customer_id": "CUST1000", "accepted": True},
                    headers=token(client, "customer"))
    assert r.status_code == 200
    out = r.json()
    assert out["ledger_index"] == 0 and len(out["ledger_hash"]) == 64
    assert out["retention_days"] > 0
    v = client.post("/ledger/verify", headers=token(client, "compliance_officer"))
    assert v.json()["ok"] is True and v.json()["records_checked"] == 1


def test_verify_reports_a_tamper_through_the_api(client):
    client.post("/session/consent", json={"customer_id": "CUST1000", "accepted": True},
                headers=token(client, "customer"))
    main.CONN.execute("UPDATE ledger SET payload='{\"x\":1}' WHERE idx=0")
    main.CONN.commit()
    out = client.post("/ledger/verify", headers=token(client, "compliance_officer")).json()
    assert out["ok"] is False and out["first_broken_index"] == 0
    assert out["broken_record_id"] and out["expected_hash"] != out["actual_hash"]


def test_trace_404_for_unknown_id(client):
    r = client.get("/trace/00000000-0000-0000-0000-000000000000",
                   headers=token(client, "compliance_officer"))
    assert r.status_code == 404


def test_metrics_shape(client):
    r = client.get("/metrics", headers=token(client, "compliance_officer"))
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"turns", "decisions", "stages", "uptime_s"}


@pytest.mark.parametrize("role", ROLES)
def test_health_needs_nothing(client, role):
    assert client.get("/health").status_code == 200
