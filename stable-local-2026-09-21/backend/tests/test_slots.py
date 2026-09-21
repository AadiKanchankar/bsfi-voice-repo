"""A3, slot rules. Amounts are the most dangerous slot in the system, so they
carry the most tests."""
import pytest

from app.pipeline import slots


@pytest.mark.parametrize("text,expected", [
    ("transfer fifty thousand rupees", 50000),
    ("pachas hazaar bhejna hai", 50000),
    ("send 2 lakh", 200000),
    ("do lakh ka NEFT karna hai", 200000),
    ("Rs 25,000 transfer to Rohan", 25000),
    ("transfer 1000 rupees", 1000),
    ("dus hazaar rupaye transfer karo", 10000),
    ("set my daily limit to one lakh", 100000),
])
def test_amounts(text, expected):
    assert slots.parse_amount(text) == expected


@pytest.mark.parametrize("text", [
    "show me my last three transactions",
    "block my card",
    "what is my balance",
])
def test_no_false_amounts(text):
    assert slots.parse_amount(text) is None


def test_card_last4():
    assert slots.extract("block card ending 4321")["card_last4"] == "4321"
    assert slots.extract("Please block my card ending in 7788")["card_last4"] == "7788"


def test_cheque_number():
    assert slots.extract("cheque number 456789 status")["cheque_number"] == "456789"


def test_payee_only_for_transfer_intents():
    assert slots.extract("Transfer ten thousand to Rohan", "fund_transfer")["payee"] == "Rohan"
    assert "payee" not in slots.extract("Transfer ten thousand to Rohan", "get_balance")


def test_date_range():
    out = slots.extract("show my last three transactions")["date_range"]
    assert out["count"] == 3 and "transaction" in out["unit"]


def test_product_slot():
    assert slots.extract("what are your home loan rates")["product"] == "home loan"
