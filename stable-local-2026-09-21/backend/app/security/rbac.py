"""Demo-scale RBAC: signed JWT, four hardcoded roles.

The production design in the synopsis names Keycloak and OAuth 2.0. This is the
same access matrix with none of the infrastructure, and the substitution is
recorded in docs/STACK_MAPPING.md. The matrix itself is the part worth testing,
and tests/test_rbac.py walks every cell of it.
"""
from __future__ import annotations

import time
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status

from ..config import JWT_ALG, JWT_SECRET, JWT_TTL_SECONDS, ROLES

# Endpoint permission -> roles allowed. A customer must never reach the export.
PERMISSIONS: dict[str, set[str]] = {
    "session:create":   {"customer", "agent", "admin"},
    "turn:submit":      {"customer", "agent", "admin"},
    "enroll":           {"customer", "agent", "admin"},
    "trace:read_own":   {"customer", "agent", "compliance_officer", "admin"},
    "trace:read_any":   {"agent", "compliance_officer", "admin"},
    "ledger:verify":    {"compliance_officer", "admin", "agent"},
    "ledger:export":    {"compliance_officer", "admin"},
    "handover:read":    {"agent", "compliance_officer", "admin"},
    "handover:claim":   {"agent", "admin"},
    "metrics:read":     {"compliance_officer", "admin", "agent"},
    "consent:withdraw": {"customer", "compliance_officer", "admin"},
    "admin:reset":      {"admin"},
}


def issue_token(subject: str, role: str, session_id: str | None = None) -> str:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    now = int(time.time())
    return jwt.encode({"sub": subject, "role": role, "sid": session_id,
                       "iat": now, "exp": now + JWT_TTL_SECONDS},
                      JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}")


def allowed(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, set())


async def current_principal(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return decode_token(authorization.split(" ", 1)[1])


def require(permission: str):
    """FastAPI dependency factory. Usage: Depends(require("ledger:export"))."""
    async def _dep(principal: Annotated[dict, Depends(current_principal)]) -> dict:
        if not allowed(principal.get("role", ""), permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role {principal.get('role')!r} may not {permission}")
        return principal
    return _dep
