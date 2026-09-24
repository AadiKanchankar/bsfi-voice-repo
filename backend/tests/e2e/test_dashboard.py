"""R2 acceptance, in a real browser.

The change request asks for two tests: an officer finds a seeded customer by
id, opens a call, sees the trace, plays a recording and runs ledger
verification; and a customer token cannot reach any of it.

They are written against the behaviour that was actually broken. The old
lookup could not report a miss, so the first thing asserted is that a wrong
id now says so. See DECISIONS.md D22.
"""
import re

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright     # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def page(stack):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        pg = ctx.new_page()
        yield pg
        ctx.close()
        browser.close()


def open_dashboard(page, stack):
    page.goto(stack["base"] + "/compliance")
    expect(page.get_by_test_id("lookup")).to_be_visible(timeout=15000)


def look_up(page, text):
    page.get_by_test_id("lookup").fill(text)
    page.get_by_test_id("lookup-go").click()


# ---------------------------------------------------------------- the fix

def test_a_wrong_identifier_says_so_instead_of_showing_nothing(page, stack, seeded_call):
    """The defect itself. This used to render a blank pane and no error."""
    open_dashboard(page, stack)
    look_up(page, "definitely-not-an-id")
    err = page.get_by_test_id("error")
    expect(err).to_be_visible(timeout=10000)
    expect(err).to_contain_text("nothing matches")
    expect(err).to_contain_text("customer id")


def test_an_officer_finds_a_customer_opens_a_call_and_reads_the_trace(
        page, stack, seeded_call):
    open_dashboard(page, stack)

    # By customer id: the dashboard lists that customer's calls.
    look_up(page, seeded_call["customer_id"])
    expect(page.get_by_test_id("note")).to_contain_text(seeded_call["customer_id"],
                                                        timeout=10000)
    row = page.get_by_test_id(f"call-{seeded_call['call_id']}")
    expect(row).to_be_visible(timeout=10000)

    # Open it, and the drill-down names the call and the customer.
    row.click()
    detail = page.get_by_test_id("call-detail")
    expect(detail).to_be_visible(timeout=10000)
    expect(detail).to_contain_text(seeded_call["call_id"])
    expect(detail).to_contain_text(seeded_call["customer_id"])

    # Its ledger records verify, each one checked rather than trusted.
    expect(page.get_by_test_id("ledger-status")).to_have_text(
        re.compile("all verified"), timeout=10000)


def test_a_partial_session_id_is_enough(page, stack, seeded_call):
    """Eight characters is all the customer console ever shows."""
    open_dashboard(page, stack)
    look_up(page, seeded_call["session_id"][:8])
    expect(page.get_by_test_id("call-detail")).to_contain_text(
        seeded_call["call_id"], timeout=15000)


def test_an_officer_plays_a_recording_and_the_play_is_logged(page, stack, seeded_call):
    open_dashboard(page, stack)
    look_up(page, seeded_call["call_id"])
    expect(page.get_by_test_id("call-detail")).to_be_visible(timeout=15000)

    play = page.get_by_test_id(f"play-{seeded_call['recording_id']}")
    expect(play).to_be_visible(timeout=10000)
    play.click()
    # The player appears only once the decrypted audio arrived and matched its
    # digest; a refusal or a digest mismatch shows the error line instead.
    expect(page.locator("audio")).to_be_visible(timeout=20000)
    expect(page.get_by_test_id("error")).to_have_count(0)

    # And the playback is in the access log, with the ledger record beside it.
    page.get_by_role("button", name="Access log").click()
    expect(page.get_by_text("play_recording", exact=False).first).to_be_visible(
        timeout=10000)


def test_ledger_verification_runs_green_from_the_dashboard(page, stack, seeded_call):
    open_dashboard(page, stack)
    page.get_by_role("button", name="Ledger", exact=True).click()
    verify = page.get_by_role("button", name=re.compile("verify", re.I)).first
    expect(verify).to_be_visible(timeout=10000)
    verify.click()
    expect(page.get_by_text(re.compile(r"intact|verified|ok", re.I)).first
           ).to_be_visible(timeout=20000)


# ---------------------------------------------------------------- the boundary

def test_a_customer_token_cannot_reach_the_lookup(page, stack, seeded_call):
    """The authorisation boundary, checked through the browser rather than
    only in the permission matrix, because a correct matrix wired to the
    wrong dependency still leaks."""
    api = stack["api"]
    token = page.request.post(api + "/auth/demo-token",
                              data={"subject": "sneaky", "role": "customer"}
                              ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    for path in ("/search?q=CUST1000", "/calls", f"/calls/{seeded_call['call_id']}",
                 "/customers/CUST1000", "/cases", "/access-log",
                 f"/recordings/{seeded_call['recording_id']}"):
        res = page.request.get(api + path, headers=headers)
        assert res.status == 403, f"{path} returned {res.status}"
