"""A1. The Viterbi smoother is deterministic, so it gets exact-value tests."""
from app.pipeline import langid


def test_monolingual_english_has_zero_cmi():
    out = langid.identify("What are your home loan interest rates")
    assert out["dominant"] == "en"
    assert out["code_mix_index"] == 0.0
    assert len(out["spans"]) == 1


def test_code_mixed_utterance_produces_multiple_spans():
    out = langid.identify("Mera balance kitna hai and last three transactions bhi bata do")
    assert len({s.lang for s in out["spans"]}) >= 2
    assert out["code_mix_index"] > 0
    assert sum(s.end_word - s.start_word for s in out["spans"]) == len(out["words"])


def test_cmi_formula():
    assert langid.code_mix_index(["en"] * 10) == 0.0
    assert langid.code_mix_index(["en"] * 5 + ["hi"] * 5) == 50.0
    assert langid.code_mix_index(["en"] * 8 + ["hi"] * 2) == 20.0
    assert langid.code_mix_index([]) == 0.0


def test_switch_penalty_reduces_flapping():
    """The point of eta: noisy near-tied posteriors must not alternate."""
    noisy = [{"en": 0.55, "hi": 0.44, "mr": 0.01},
             {"en": 0.45, "hi": 0.54, "mr": 0.01}] * 4
    assert len(set(langid.viterbi_smooth(noisy, eta=0.0))) == 2
    assert len(set(langid.viterbi_smooth(noisy, eta=3.0))) == 1


def test_strong_evidence_survives_the_penalty():
    """eta must not be so blunt that a real switch is erased."""
    strong = ([{"en": 0.98, "hi": 0.01, "mr": 0.01}] * 4 +
              [{"en": 0.01, "hi": 0.98, "mr": 0.01}] * 4)
    labels = langid.viterbi_smooth(strong, eta=2.0)
    assert labels == ["en"] * 4 + ["hi"] * 4


def test_devanagari_is_never_english():
    out = langid.identify("मेरा बैलेंस कितना है")
    assert out["dominant"] in ("hi", "mr")
    assert all(l != "en" for l in out["labels"])


def test_empty_input():
    out = langid.identify("")
    assert out["spans"] == [] and out["code_mix_index"] == 0.0
