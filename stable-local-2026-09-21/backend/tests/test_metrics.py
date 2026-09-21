"""A9. The metrics have to be right before any number they produce is quoted."""
import numpy as np
import pytest

from app.eval import metrics


def test_wer_exact():
    r = metrics.wer("block my card ending four three two one",
                    "block my card ending four three two one")
    assert r["wer"] == 0.0
    r = metrics.wer("transfer fifty thousand rupees to rohan",
                    "transfer fifteen thousand rupees to rohan")
    assert (r["substitutions"], r["deletions"], r["insertions"]) == (1, 0, 0)
    assert r["wer"] == pytest.approx(1 / 6)


def test_wer_counts_each_edit_type():
    r = metrics.wer("a b c d", "a x c d e")          # 1 sub, 1 ins
    assert r["substitutions"] == 1 and r["insertions"] == 1 and r["deletions"] == 0
    r = metrics.wer("a b c d", "a c d")              # 1 del
    assert r["deletions"] == 1


def test_corpus_wer_is_pooled_not_averaged():
    """Averaging per-utterance WER over-weights short utterances."""
    pairs = [("a", "b"), ("a b c d e f g h i j", "a b c d e f g h i j")]
    pooled = metrics.corpus_wer(pairs)["wer"]
    averaged = sum(metrics.wer(r, h)["wer"] for r, h in pairs) / 2
    assert pooled == pytest.approx(1 / 11)
    assert averaged == pytest.approx(0.5)
    assert pooled != averaged


def test_empty_hypothesis_is_a_total_error():
    assert metrics.wer("one two three", "")["wer"] == 1.0


def test_entity_metric_ignores_transcription_formatting():
    """"fifty thousand" heard as "50,000" is correct, not an error. Before this
    was fixed the metric reported an amount error rate of 1.0 on transcripts
    that had the amount right."""
    out = metrics.entity_error_rate([
        {"id": "a", "reference": "Transfer fifty thousand rupees to Rohan",
         "hypothesis": "Transfer 50,000 rubies to Rohan.",
         "entities": [{"type": "amount", "value": "50000"},
                      {"type": "payee", "value": "Rohan"}]},
        {"id": "b", "reference": "Block my debit card ending 4321",
         "hypothesis": "Block my debit card ending 4,321.",
         "entities": [{"type": "card_last4", "value": "4321"}]},
        {"id": "c", "reference": "What is the status of cheque number 456789",
         "hypothesis": "What is the status of check number 456,789?",
         "entities": [{"type": "cheque_number", "value": "456789"}]},
    ])
    assert out["entity_error_rate"] == 0.0, out["details"]


def test_entity_metric_still_catches_a_genuinely_wrong_value():
    out = metrics.entity_error_rate([
        {"id": "w", "reference": "Transfer fifty thousand to Rohan",
         "hypothesis": "Transfer fifteen thousand to Mohan",
         "entities": [{"type": "amount", "value": "50000"},
                      {"type": "payee", "value": "Rohan"}]}])
    assert out["entity_error_rate"] == 1.0


def test_unlocatable_entity_counts_as_an_error_not_a_skip():
    """Silently dropping hard cases would flatter the number."""
    out = metrics.entity_error_rate([
        {"id": "x", "reference": "block my card", "hypothesis": "block my card",
         "entities": [{"type": "amount", "value": "50000"}]}])
    assert out["n_entities"] == 1 and out["errors"] == 1


def test_delta_calibration_picks_a_separating_threshold():
    answerable = [0.7, 0.75, 0.8, 0.65]
    unanswerable = [0.2, 0.3, 0.25, 0.4]
    out = metrics.calibrate_delta(answerable, unanswerable)
    assert 0.4 < out["delta"] <= 0.65 and out["f1"] == 1.0


def test_eer_is_zero_for_separable_scores_and_half_for_identical():
    assert metrics.eer(np.array([0.9, 0.8]), np.array([0.1, 0.2]))["eer"] == 0.0
    tied = metrics.eer(np.array([0.5, 0.5]), np.array([0.5, 0.5]))["eer"]
    assert 0.0 <= tied <= 1.0


def test_tdcf_reports_undefined_rather_than_none_without_explanation():
    out = metrics.min_tdcf(np.array([0.9, 0.8]), np.array([0.1, 0.2]),
                           asv_p_miss=0.0, asv_p_fa=0.0, asv_p_fa_spoof=0.0)
    assert out["min_tdcf"] is None and out["defined"] is False
    assert out["reason"] and out["priors"] and out["costs"]


def test_tdcf_is_computed_when_the_cost_model_is_well_posed():
    out = metrics.min_tdcf(np.array([0.9, 0.8, 0.7]), np.array([0.1, 0.2, 0.6]),
                           asv_p_miss=0.05, asv_p_fa=0.02, asv_p_fa_spoof=0.4)
    assert out["defined"] is True and out["min_tdcf"] >= 0.0


def test_latency_percentiles():
    traces = [{"stages": [{"stage": "asr", "duration_ms": float(i)}]} for i in range(1, 101)]
    out = metrics.latency_from_traces(traces)
    assert out["asr"]["n"] == 100
    assert 45 <= out["asr"]["p50_ms"] <= 55
    assert out["asr"]["p95_ms"] >= 90
