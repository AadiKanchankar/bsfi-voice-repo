"""R5. Cloud speech providers, and the local stack underneath them.

The property that matters is not that a vendor works. It is that the system
keeps working when the vendor does not: no key, an error, or simply too slow
to start speaking. A demo in a review room with bad WiFi should sound worse,
never fail.
"""
import pytest

from app.capabilities import CAPABILITIES
from app.pipeline import providers as pv


@pytest.fixture(autouse=True)
def _clean():
    pv.reset_usage()
    yield
    pv.reset_usage()


# ---------------------------------------------------------------- fallback

def test_without_a_key_a_cloud_provider_reports_itself_unavailable(monkeypatch):
    monkeypatch.delenv("BFSI_SARVAM_API_KEY", raising=False)
    monkeypatch.delenv("BFSI_ELEVENLABS_API_KEY", raising=False)
    for name in ("sarvam", "elevenlabs"):
        h = pv._registry()[name].health()
        assert h.available is False
        assert "no API key" in h.reason
        # And it says which variable, so the fix is obvious.
        assert "BFSI_" in h.reason


def test_the_local_stack_is_always_available():
    h = pv._registry()["local"].health()
    assert h.available is True
    assert h.leaves_machine is False


def test_selection_falls_back_to_local_when_the_provider_has_no_key(monkeypatch):
    monkeypatch.delenv("BFSI_SARVAM_API_KEY", raising=False)
    monkeypatch.setitem(pv.TTS_PROVIDER_BY_LANGUAGE, "hi", "sarvam")
    assert pv.tts_for("hi").name == "local"
    assert pv.usage("sarvam").fallbacks >= 1


def test_an_unknown_provider_name_does_not_crash_the_turn(monkeypatch):
    monkeypatch.setitem(pv.TTS_PROVIDER_BY_LANGUAGE, "en", "nonsense")
    assert pv.tts_for("en").name == "local"


@pytest.mark.slow
def test_speaking_falls_back_and_says_which_engine_answered(monkeypatch):
    """The dashboard has to be able to tell the truth about what spoke."""
    monkeypatch.delenv("BFSI_SARVAM_API_KEY", raising=False)
    monkeypatch.setitem(pv.TTS_PROVIDER_BY_LANGUAGE, "en", "sarvam")
    out = pv.speak("Your account is active.", "en")
    assert out["provider"] == "local"
    assert out["leaves_machine"] is False
    assert out["audio"]


@pytest.mark.slow
def test_the_local_stack_streams_phrase_by_phrase():
    """R4's win depends on this: the first phrase plays while the rest is
    still being made."""
    out = pv.speak("Your balance is ready. Anything else today?", "en")
    assert out["chunks"] >= 2, out


# ---------------------------------------------------------------- honesty

def test_cloud_providers_are_registered_external_with_a_note_saying_what_leaves():
    for key in ("tts_sarvam", "stt_sarvam", "tts_elevenlabs"):
        cap = CAPABILITIES[key]
        assert cap.external is True, key
        assert cap.note and "leaves this machine" in cap.note, key


def test_sarvam_is_simulated_until_it_has_actually_run():
    """It has never been called. Listing it REAL because the code exists
    would be exactly the dishonesty the registry is there to prevent."""
    for key in ("tts_sarvam", "stt_sarvam"):
        assert CAPABILITIES[key].status == "SIMULATED", key
        assert "never run against the service" in CAPABILITIES[key].note \
            or "SIMULATED for the same reason" in CAPABILITIES[key].note


def test_the_vendor_latency_claim_is_not_repeated_as_ours():
    note = CAPABILITIES["tts_elevenlabs"].note
    assert "model inference only" in note
    assert "RESULTS.md" in note


def test_the_local_stack_is_not_marked_external():
    assert CAPABILITIES["tts"].external is False
    assert CAPABILITIES["asr"].external is False


# ---------------------------------------------------------------- usage

def test_usage_is_metered_because_these_apis_bill_per_use():
    pv.usage("elevenlabs").characters_synthesised += 120
    pv.usage("elevenlabs").calls += 1
    report = pv.usage_report()
    assert report["elevenlabs"]["characters_synthesised"] == 120
    assert report["elevenlabs"]["calls"] == 1


def test_the_health_report_names_the_provider_chosen_per_language():
    report = pv.health_report()
    assert set(report["selected"]) == {"en", "hi", "mr"}
    assert set(report["tts"]) >= {"local", "sarvam", "elevenlabs"}
