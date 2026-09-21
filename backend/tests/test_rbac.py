"""Section 8. The role matrix, walked cell by cell.

The cell that matters most: a customer token must not be able to read
/ledger/export. That one is called out separately below as well.
"""
import pytest

from app.config import ROLES
from app.security import rbac

EXPECTED = {
    "customer":           {"session:create", "turn:submit", "enroll", "trace:read_own",
                           "consent:withdraw"},
    "agent":              {"session:create", "turn:submit", "enroll", "trace:read_own",
                           "trace:read_any", "ledger:verify", "handover:read",
                           "handover:claim", "metrics:read"},
    "compliance_officer": {"trace:read_own", "trace:read_any", "ledger:verify",
                           "ledger:export", "handover:read", "metrics:read",
                           "consent:withdraw"},
    "admin":              set(rbac.PERMISSIONS),
}


@pytest.mark.parametrize("role", ROLES)
def test_role_matrix_is_exactly_as_documented(role):
    granted = {p for p in rbac.PERMISSIONS if rbac.allowed(role, p)}
    assert granted == EXPECTED[role], (
        f"{role}: unexpected {granted - EXPECTED[role]}, missing {EXPECTED[role] - granted}")


def test_customer_cannot_export_the_ledger():
    assert rbac.allowed("customer", "ledger:export") is False
    assert rbac.allowed("compliance_officer", "ledger:export") is True


def test_customer_cannot_claim_a_handover():
    assert rbac.allowed("customer", "handover:claim") is False


def test_only_admin_may_reset():
    for role in ROLES:
        assert rbac.allowed(role, "admin:reset") is (role == "admin")


def test_token_round_trip():
    token = rbac.issue_token("demo-user", "compliance_officer", "sess-1")
    claims = rbac.decode_token(token)
    assert claims["sub"] == "demo-user" and claims["role"] == "compliance_officer"


def test_unknown_role_is_rejected_at_issue():
    with pytest.raises(ValueError):
        rbac.issue_token("x", "superuser")


def test_tampered_token_is_rejected():
    from fastapi import HTTPException
    token = rbac.issue_token("demo-user", "customer")
    head, payload, sig = token.split(".")
    forged = f"{head}.{payload}.{'A' * len(sig)}"
    with pytest.raises(HTTPException):
        rbac.decode_token(forged)


def test_unknown_permission_grants_nobody():
    for role in ROLES:
        assert rbac.allowed(role, "ledger:delete") is False
