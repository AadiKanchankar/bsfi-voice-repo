"""The mock core banking layer. SIMULATED, but its lookups still have to work."""
import pytest

from app import db
from app.banking.mock_core import MockCore


@pytest.fixture()
def core(conn):
    for ifsc, name, city, addr in [
        ("DEMO0001234", "Nigdi", "Pune", "Sector 26, Pradhikaran, Nigdi, Pune 411044"),
        ("DEMO0001235", "Kothrud", "Pune", "Paud Road, Kothrud, Pune 411038"),
        ("DEMO0002101", "Andheri East", "Mumbai", "Chakala, Andheri East, Mumbai 400099"),
    ]:
        conn.execute("INSERT INTO branches (ifsc, name, city, address) VALUES (?,?,?,?)",
                     (ifsc, name, city, addr))
    conn.commit()
    return MockCore(conn)


def test_branch_lookup_matches_words_not_the_whole_sentence(core):
    """A LIKE pattern built from the entire utterance matches nothing, which
    silently sent every branch question to the policy document instead."""
    out = core.find_branch("What is the IFSC code of the Nigdi branch")
    assert out and out[0]["ifsc"] == "DEMO0001234"


def test_branch_lookup_by_city_and_by_code(core):
    assert {b["city"] for b in core.find_branch("branches in Pune")} == {"Pune"}
    assert core.find_branch("DEMO0002101")[0]["name"] == "Andheri East"


def test_branch_lookup_in_a_code_mixed_question(core):
    out = core.find_branch("Kothrud shakhecha IFSC code sanga")
    assert out and out[0]["name"] == "Kothrud"


def test_branch_lookup_returns_nothing_for_an_unknown_place(core):
    assert core.find_branch("Chennai") == []


def test_stopwords_alone_match_nothing(core):
    """Otherwise "what is the branch" would return an arbitrary branch."""
    assert core.find_branch("what is the branch address") == []


def test_transfer_declines_when_funds_are_short(conn):
    conn.execute("INSERT INTO accounts (account_id, customer_id, account_number,"
                 " account_type, balance) VALUES ('A1','C1','123456789012','savings',500)")
    conn.execute("INSERT INTO payees (payee_id, customer_id, name, account_number)"
                 " VALUES ('P1','C1','Rohan','999999999999')")
    conn.commit()
    out = MockCore(conn).transfer("A1", "P1", 5000)
    assert out["status"] == "declined" and out["reason"] == "insufficient funds"
    assert conn.execute("SELECT balance FROM accounts WHERE account_id='A1'").fetchone()[0] == 500


def test_transfer_debits_and_records_a_transaction(conn):
    conn.execute("INSERT INTO accounts (account_id, customer_id, account_number,"
                 " account_type, balance) VALUES ('A1','C1','123456789012','savings',5000)")
    conn.execute("INSERT INTO payees (payee_id, customer_id, name, account_number)"
                 " VALUES ('P1','C1','Rohan','999999999999')")
    conn.commit()
    core = MockCore(conn)
    out = core.transfer("A1", "P1", 1500)
    assert out["status"] == "completed" and out["balance_after"] == 3500
    assert core.get_balance("A1")["balance"] == 3500
    assert len(core.get_transactions("A1", 5)) == 1


def test_block_card_is_reflected_in_the_store(conn):
    conn.execute("INSERT INTO cards (card_id, customer_id, card_number, card_type, status)"
                 " VALUES ('C1','CUST1','4111111111111111','debit','active')")
    conn.commit()
    core = MockCore(conn)
    assert core.block_card("C1")["status"] == "blocked"
    assert core.find_card("CUST1", "1111")["status"] == "blocked"
