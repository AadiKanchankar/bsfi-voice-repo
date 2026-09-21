"""SIMULATED core banking. Registered as SIMULATED in capabilities.py, and the
dashboard marks every stage that touches it.

The interface is documented rather than clever: a real core banking adapter
would implement the same six methods over ISO 8583 or a REST gateway, and
nothing above this layer would change. That is the point of writing it down.

    get_customer(customer_id)                  -> dict | None
    get_accounts(customer_id)                  -> list[dict]
    get_balance(account_id)                    -> dict
    get_transactions(account_id, limit)        -> list[dict]
    get_cards(customer_id)                     -> list[dict]
    block_card(card_id)                        -> dict
    set_card_limit(card_id, limit)             -> dict
    add_payee(customer_id, name, acct, ifsc)   -> dict
    transfer(from_account, payee_id, amount)   -> dict
    get_cheque(cheque_number)                  -> dict | None
    find_branch(query)                         -> list[dict]

No method here makes a decision. Decisions happen in dialogue.py and are
recorded in the trace before any of this is called.
"""
from __future__ import annotations

import re
import sqlite3
import uuid

from ..trace import utcnow


class MockCore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -------------------------------------------------------- reads
    def get_customer(self, customer_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM customers WHERE customer_id=?",
                                (customer_id,)).fetchone()
        return dict(row) if row else None

    def get_accounts(self, customer_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM accounts WHERE customer_id=?", (customer_id,))]

    def primary_account(self, customer_id: str) -> dict | None:
        accts = self.get_accounts(customer_id)
        return accts[0] if accts else None

    def get_balance(self, account_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM accounts WHERE account_id=?",
                                (account_id,)).fetchone()
        if not row:
            raise KeyError(f"no such account {account_id}")
        return {"account_id": account_id, "balance": row["balance"],
                "account_number": row["account_number"],
                "account_type": row["account_type"], "currency": "INR"}

    def get_transactions(self, account_id: str, limit: int = 3) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM transactions WHERE account_id=? ORDER BY ts DESC LIMIT ?",
            (account_id, limit))]

    def get_cards(self, customer_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM cards WHERE customer_id=?", (customer_id,))]

    def find_card(self, customer_id: str, last4: str | None) -> dict | None:
        cards = self.get_cards(customer_id)
        if last4:
            for c in cards:
                if c["card_number"].endswith(last4):
                    return c
            return None
        active = [c for c in cards if c["status"] == "active"]
        return active[0] if active else (cards[0] if cards else None)

    def get_cheque(self, cheque_number: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM cheques WHERE cheque_number=?",
                                (cheque_number,)).fetchone()
        return dict(row) if row else None

    # Words that appear in every branch question and match nothing useful.
    _BRANCH_STOPWORDS = {
        "what", "is", "the", "of", "your", "a", "an", "in", "at", "for", "me",
        "my", "code", "ifsc", "branch", "branches", "address", "give", "tell",
        "find", "where", "nearest", "please", "and", "shakha", "shakhecha",
        "kuthe", "kahan", "batao", "sanga", "chahiye", "pahije", "micr",
    }

    def find_branch(self, query: str) -> list[dict]:
        """Match on the words of the question, not the whole sentence.

        A LIKE pattern built from the entire utterance matches nothing, which
        made every branch question fall through to the policy document even
        though the branch table had the answer.
        """
        words = [w for w in re.findall(r"[\w]+", (query or "").lower())
                 if w not in self._BRANCH_STOPWORDS and len(w) > 2]
        if not words:
            return []
        clauses = " OR ".join(["name LIKE ? OR city LIKE ? OR ifsc LIKE ?"] * len(words))
        params: list[str] = []
        for w in words:
            params.extend([f"%{w}%"] * 3)
        return [dict(r) for r in self.conn.execute(
            f"SELECT * FROM branches WHERE {clauses} LIMIT 5", params)]

    def get_payees(self, customer_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM payees WHERE customer_id=?", (customer_id,))]

    def get_holdings(self, customer_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM holdings WHERE customer_id=? ORDER BY kind, name",
            (customer_id,))]

    def portfolio_value(self, customer_id: str) -> dict:
        """Current value, cost and unrealised gain. Facts only: nothing here
        is a view on whether any of it was a good idea."""
        rows = self.get_holdings(customer_id)
        value = sum(r["units"] * r["last_price"] for r in rows)
        cost = sum(r["units"] * r["avg_cost"] for r in rows)
        by_kind: dict[str, float] = {}
        for r in rows:
            by_kind[r["kind"]] = by_kind.get(r["kind"], 0.0) + r["units"] * r["last_price"]
        return {"n_holdings": len(rows), "value": round(value, 2),
                "cost": round(cost, 2), "unrealised": round(value - cost, 2),
                "by_kind": {k: round(v, 2) for k, v in by_kind.items()},
                "as_of": rows[0]["as_of"] if rows else None}

    def find_holding(self, customer_id: str, needle: str) -> dict | None:
        needle = (needle or "").strip().lower()
        if not needle:
            return None
        for r in self.get_holdings(customer_id):
            if needle in r["name"].lower():
                return r
        return None

    def get_sips(self, customer_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM sips WHERE customer_id=? AND status='active'", (customer_id,))]

    # -------------------------------------------------------- writes
    def block_card(self, card_id: str) -> dict:
        self.conn.execute("UPDATE cards SET status='blocked' WHERE card_id=?", (card_id,))
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
        return {"card_id": card_id, "status": row["status"],
                "last4": row["card_number"][-4:], "blocked_at": utcnow().isoformat()}

    def set_card_limit(self, card_id: str, limit: float) -> dict:
        self.conn.execute("UPDATE cards SET daily_limit=? WHERE card_id=?", (limit, card_id))
        self.conn.commit()
        return {"card_id": card_id, "daily_limit": limit,
                "effective_from": utcnow().isoformat()}

    def add_payee(self, customer_id: str, name: str, account_number: str,
                  ifsc: str | None = None) -> dict:
        pid = f"PAY{uuid.uuid4().hex[:8].upper()}"
        self.conn.execute(
            "INSERT INTO payees (payee_id, customer_id, name, account_number, ifsc, added_at)"
            " VALUES (?,?,?,?,?,?)",
            (pid, customer_id, name, account_number, ifsc, utcnow().isoformat()))
        self.conn.commit()
        return {"payee_id": pid, "name": name, "account_last4": account_number[-4:]}

    def transfer(self, from_account: str, payee_id: str, amount: float) -> dict:
        bal = self.get_balance(from_account)["balance"]
        if amount > bal:
            return {"status": "declined", "reason": "insufficient funds",
                    "balance": bal, "amount": amount}
        txn_id = f"TXN{uuid.uuid4().hex[:10].upper()}"
        self.conn.execute("UPDATE accounts SET balance=balance-? WHERE account_id=?",
                          (amount, from_account))
        self.conn.execute(
            "INSERT INTO transactions (txn_id, account_id, ts, amount, direction, description, channel)"
            " VALUES (?,?,?,?,?,?,?)",
            (txn_id, from_account, utcnow().isoformat(), amount, "debit",
             f"Transfer to {payee_id}", "voice-assistant"))
        self.conn.commit()
        return {"status": "completed", "txn_id": txn_id, "amount": amount,
                "balance_after": bal - amount}
