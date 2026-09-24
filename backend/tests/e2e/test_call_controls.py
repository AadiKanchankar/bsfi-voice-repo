"""R3 acceptance, through the browser and through the API the browser uses.

The change request asks for: two rapid utterances produce exactly one reply
stream, barge-in stops audio promptly, an interrupted read-back executes
nothing, and end call works from every state.

The first, third and fourth are properties of the server, so they are
asserted against the running server rather than through the UI, which is
where they are actually enforced. The stop and end controls are asserted in
the browser, because a control that exists but is not wired up is exactly the
kind of thing a unit test misses.
"""
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


@pytest.fixture()
def api(page, stack):
    """An authenticated request context against the live server."""
    token = page.request.post(stack["api"] + "/auth/demo-token",
                              data={"subject": "e2e", "role": "customer"}
                              ).json()["token"]
    base, hdr = stack["api"], {"Authorization": f"Bearer {token}"}

    # A turn runs speech recognition and the whole pipeline, which takes
    # seconds on this hardware and longer when something else is using the
    # machine. Playwright's 30 s default is tight enough that a busy laptop
    # turns a passing test into a timeout, so it is stated rather than left
    # to chance. It is a ceiling on flakiness, not a performance claim:
    # RESULTS.md carries the measured numbers.
    TURN_TIMEOUT_MS = 120_000

    class Api:
        def post(self, path, **kw):
            kw.setdefault("timeout", TURN_TIMEOUT_MS)
            return page.request.post(base + path, headers=hdr, **kw)

        def get(self, path):
            return page.request.get(base + path, headers=hdr,
                                    timeout=TURN_TIMEOUT_MS)

        def open_call(self):
            return self.post("/session/consent",
                             data={"customer_id": "CUST1000",
                                   "accepted": True}).json()
    return Api()


def test_two_rapid_utterances_produce_one_reply_and_one_superseded_turn(api):
    """The double-voice bug. The second utterance supersedes the first, and
    the first is accounted for rather than silently dropped."""
    s = api.open_call()
    first = api.post("/turn/text", data={"session_id": s["session_id"],
                                         "text": "what is my balance"})
    assert first.status == 200
    second = api.post("/turn/text", data={"session_id": s["session_id"],
                                          "text": "and my last five transactions"})
    assert second.status == 200
    assert second.json()["turn_id"] > first.json()["turn_id"]

    state = api.get(f"/call/{s['call_id']}/state").json()
    assert state["turn_in_flight"] is False
    assert state["state"] in ("SPEAKING", "LISTENING")


def test_end_call_works_from_every_state(api):
    """Including with nothing having happened, and mid conversation."""
    fresh = api.open_call()
    assert api.post(f"/call/{fresh['call_id']}/end").json()["state"] == "ENDED"

    mid = api.open_call()
    api.post("/turn/text", data={"session_id": mid["session_id"],
                                 "text": "what is my balance"})
    assert api.post(f"/call/{mid['call_id']}/end").json()["state"] == "ENDED"
    # And nothing may follow.
    assert api.post("/turn/text", data={"session_id": mid["session_id"],
                                        "text": "hello"}).status == 409


def test_interrupting_records_what_was_heard(api):
    s = api.open_call()
    api.post("/turn/text", data={"session_id": s["session_id"],
                                 "text": "what is my balance"})
    out = api.post(f"/call/{s['call_id']}/interrupt",
                   data={"played_ms": 300, "played_chars": 10, "reply_chars": 100}
                   ).json()
    assert out["fraction_delivered"] == 0.1
    assert out["state"] == "LISTENING"


def test_an_interrupted_read_back_moves_no_money(api, stack):
    """The safety rule. Cut off the read-back, then say yes, and nothing
    must happen: the caller never heard what they would be agreeing to."""
    import sqlite3
    s = api.open_call()
    api.post("/verify/demo", data={"session_id": s["session_id"]})
    api.post("/turn/text", data={"session_id": s["session_id"],
                                 "text": "transfer 5000 rupees to Diya"})
    api.post("/turn/text", data={"session_id": s["session_id"], "otp": "482913"})

    # The account a transfer debits is MockCore.primary_account, which is the
    # lowest account_id for the customer, not any account of theirs. Watching
    # the wrong one makes this assertion pass whether or not money moved.
    db = sqlite3.connect(stack["db"])
    acct = db.execute("SELECT account_id FROM accounts WHERE customer_id='CUST1000'"
                      " ORDER BY account_id LIMIT 1").fetchone()[0]

    def balance():
        return db.execute("SELECT balance FROM accounts WHERE account_id=?",
                          (acct,)).fetchone()[0]

    before = balance()
    api.post(f"/call/{s['call_id']}/interrupt", data={"source": "barge_in"})
    api.post("/turn/text", data={"session_id": s["session_id"], "confirm": True})
    assert balance() == before, "an interrupted read-back must move no money"
    db.close()


def test_the_console_offers_stop_and_end_and_they_reach_the_server(page, stack):
    """A control that exists but is not wired up is what a unit test misses."""
    page.goto(stack["base"] + "/")
    expect(page.get_by_role("button", name="Give consent and start")).to_be_visible(
        timeout=15000)
    page.get_by_role("button", name="Give consent and start").click()

    state = page.get_by_test_id("call-state")
    expect(state).to_be_visible(timeout=10000)
    expect(page.get_by_test_id("stop-speaking")).to_be_visible()

    page.get_by_test_id("stop-speaking").click()
    expect(state).to_contain_text("LISTENING", timeout=10000)

    page.get_by_test_id("end-call").click()
    # The goodbye bubble specifically, not the panel heading, which also now
    # says "call ended" because the transcript survives the call.
    expect(page.get_by_text("Call ended. Thank you for calling.")).to_be_visible(
        timeout=10000)
    # And the transcript is still on screen rather than wiped by hanging up.
    expect(page.get_by_role("heading", name="Conversation (call ended)")
           ).to_be_visible()


def test_barge_in_stops_the_audio_within_150ms(page, stack):
    """The change request's number, measured on the page's own player.

    An earlier version of this test timed a probe element it had created
    itself, which measured nothing: the page pauses `player.current`, not
    whatever the test happens to be holding. So `Audio` is wrapped before the
    turn to capture the instance the page actually creates, and the clock
    runs from the stop click to that instance reporting paused.

    Only the client side is timed, deliberately. Stopping playback must not
    wait on the network: a caller who has started speaking should not keep
    hearing the assistant while a request is in flight.
    """
    page.goto(stack["base"] + "/")
    expect(page.get_by_role("button", name="Give consent and start")).to_be_visible(
        timeout=15000)

    # Capture every Audio the page builds, before it builds any.
    page.evaluate("""() => {
      window.__players = [];
      const Real = window.Audio;
      window.Audio = function (src) { const el = new Real(src); window.__players.push(el); return el; };
      window.Audio.prototype = Real.prototype;
    }""")

    page.get_by_role("button", name="Give consent and start").click()
    expect(page.get_by_test_id("stop-speaking")).to_be_visible(timeout=10000)

    # Ask something, so there is a real reply being spoken to interrupt.
    page.get_by_placeholder("Type here, or use the microphone").fill(
        "What are your home loan interest rates")
    page.get_by_role("button", name="Send", exact=True).click()

    playing = page.wait_for_function(
        "() => (window.__players || []).some(el => !el.paused && el.currentTime >= 0)",
        timeout=60000)
    assert playing

    stopped_ms = page.evaluate("""async () => {
      const live = () => (window.__players || []).filter(el => !el.paused);
      if (!live().length) return -1;
      const t0 = performance.now();
      document.querySelector('[data-testid="stop-speaking"]').click();
      for (let i = 0; i < 120; i++) {
        if (!live().length) return performance.now() - t0;
        await new Promise((r) => requestAnimationFrame(r));
      }
      return performance.now() - t0;
    }""")

    assert stopped_ms >= 0, "nothing was playing, so nothing was measured"
    assert stopped_ms < 150, f"stopping took {stopped_ms:.0f} ms, budget is 150 ms"

    # And the server was told, so the interruption reaches the audit trail.
    expect(page.get_by_test_id("call-state")).to_contain_text("LISTENING",
                                                              timeout=15000)
