"""Every tunable number in the system lives here.

Rule for this file: if a value influences a decision the compliance dashboard
shows, it is named here and nowhere else. No magic numbers inline in the
pipeline. The docs in docs/ALGORITHMS.md cite these names directly.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("BFSI_DATA_DIR", ROOT / "data"))
MODEL_DIR = Path(os.environ.get("BFSI_MODEL_DIR", ROOT / "models"))
RUNTIME_DIR = Path(os.environ.get("BFSI_RUNTIME_DIR", ROOT / "runtime"))
DB_PATH = Path(os.environ.get("BFSI_DB", RUNTIME_DIR / "bfsi.db"))
VAULT_DIR = RUNTIME_DIR / "vault"          # AES-256-GCM encrypted PII vault
POLICY_KB_DIR = DATA_DIR / "policy_kb"
SEED_DIR = DATA_DIR / "seed"
EVAL_DIR = DATA_DIR / "eval"

SEED = 20260920            # fixed seed, all synthetic data is reproducible

# ---------------------------------------------------------------- A1 language id
LANGUAGES = ["en", "hi", "mr"]
SWITCH_PENALTY_ETA = 2.0   # Viterbi penalty for changing language between words
LANGID_FLOOR = 1e-6        # posterior floor so log() stays finite

# ---------------------------------------------------------------- A2 confidence fusion
# c_final = c_asr^alpha * c_intent^beta * c_retr^gamma,  alpha+beta+gamma = 1
FUSION_ALPHA = 0.30        # ASR
FUSION_BETA = 0.45         # intent
FUSION_GAMMA = 0.25        # retrieval
assert abs(FUSION_ALPHA + FUSION_BETA + FUSION_GAMMA - 1.0) < 1e-9

# ---------------------------------------------------------------- A3 NLU
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBED_DIM = 384
INTENTS = [
    "get_balance", "mini_statement", "cheque_status", "branch_ifsc",
    "product_info", "block_card", "limit_change", "add_payee",
    "fund_transfer", "apply_loan", "dispute_txn", "fraud_report",
    "agent_request", "out_of_scope",
]
# Two different things, deliberately kept apart.
# RETRIEVAL_INTENTS run a policy search, because a passage is useful context.
# GROUNDED_INTENTS additionally refuse when nothing clears the floor, because
# there is no other authoritative source for the answer. A cheque status comes
# from the cheque table and a branch IFSC from the branch table, so those
# search the policy KB for a fallback but are not blocked when it finds
# nothing. Conflating the two made the assistant refuse questions it could
# answer from the core banking data.
RETRIEVAL_INTENTS = {"product_info", "apply_loan", "branch_ifsc", "cheque_status",
                     "out_of_scope"}
GROUNDED_INTENTS = {"product_info", "apply_loan"}

# ---------------------------------------------------------------- A4 retrieval
RETRIEVAL_K = 4
MMR_LAMBDA = 0.7
# Similarity floor. Calibrated by scripts/calibrate.py on data/eval/retrieval.json;
# the tuned value is written back to RUNTIME_DIR/calibration.json and overrides
# this default at import time (see _load_calibration below).
SIMILARITY_FLOOR_DELTA = 0.42

# ---------------------------------------------------------------- A5 risk
RISK_WEIGHTS = {"sens": 0.40, "amount": 0.25, "verify": 0.25, "history": 0.10}
assert abs(sum(RISK_WEIGHTS.values()) - 1.0) < 1e-9

INTENT_SENSITIVITY = {
    "product_info": 0.05,
    "branch_ifsc": 0.05,
    "cheque_status": 0.20,
    "apply_loan": 0.25,
    "get_balance": 0.35,
    "mini_statement": 0.35,
    "add_payee": 0.55,
    "limit_change": 0.60,
    "block_card": 0.70,
    "fund_transfer": 0.85,
    "dispute_txn": 0.90,
    "agent_request": 0.90,
    "fraud_report": 1.00,
    "out_of_scope": 0.10,
}
AMOUNT_MAX = 200_000.0     # A_max in norm(amount) = min(1, log1p(a)/log1p(A_max))
HISTORY_LAMBDA = 0.5       # dev(history) = 1 - exp(-lam * anomalies)

# Intents that need no identity at all. For these there is no verification
# deficit, so the (1 - s_verify) term contributes zero rather than a full 0.25.
# Without this, an unverified turn always scores at least 0.25 = t1 and tier 0
# is unreachable, which contradicts "tier 0: public information, no
# authentication". See docs/ARCHITECTURE.md conflict C9.
PUBLIC_INTENTS = {"product_info", "branch_ifsc", "out_of_scope"}

# Floor on the tier by intent, independent of the score. The score may raise a
# turn above its floor but never below it. This is the same mechanism as the
# tier 3 hard override, applied one level down: an action that mutates account
# state never drops below the confirmation tier however confident the system
# is about who is speaking.
MIN_TIER_BY_INTENT = {
    "get_balance": 1, "mini_statement": 1, "cheque_status": 1, "apply_loan": 1,
    "block_card": 2, "limit_change": 2, "add_payee": 2, "fund_transfer": 2,
    "fraud_report": 3, "dispute_txn": 3, "agent_request": 3,
}

TIER_CUTPOINTS = (0.25, 0.50, 0.75)      # t1, t2, t3
TIER_TAU = (0.50, 0.62, 0.75, 1.01)      # tier 3 tau is unreachable by design
# These three bypass the score entirely. A scoring bug must never automate them.
HARD_TIER3_INTENTS = {"fraud_report", "dispute_txn", "agent_request"}
# ---------------------------------------------------------------- ratchet guards
# The session tier ratchet stops an attacker lowering their own risk by asking
# an innocent question after a refused transfer. Left unguarded it also means
# ONE garbled transcript ruins the whole call: a misheard "mera balance kitna
# hai" classified as dispute_txn pins the session at tier 3 and every later
# turn escalates, including public-information questions. Observed in testing.
# Three guards keep the safety property without that failure mode.

# 1. An escalation only raises the session floor when the system was actually
#    confident about what it heard. Below this, the turn still escalates (safe),
#    but it does not poison the rest of the session.
RATCHET_MIN_INTENT_CONFIDENCE = 0.55

# 2. Public-information intents ignore the floor. They touch no account and
#    reveal nothing identity-bound, so answering one at tier 0 after an
#    escalation leaks nothing an attacker could not read on the website.
RATCHET_EXEMPT_INTENTS = PUBLIC_INTENTS

# 3. The floor decays one tier for every this-many consecutive turns that raise
#    no new escalation, so a single misfire fades instead of lasting all call.
RATCHET_DECAY_AFTER_CLEAN_TURNS = 3

TIER_REQUIRING_VERIFICATION = 1          # tier >= 1 needs speaker verification
TIER_REQUIRING_OTP = 2                   # tier >= 2 needs OTP + spoken read-back

# ---------------------------------------------------------------- A6 speaker
SPEAKER_MODEL = "speechbrain/spkrec-ecapa-voxceleb"
# theta is set at the measured EER on the synthetic trial set by `make eval`,
# which writes it to RUNTIME_DIR/calibration.json. This default is only used
# before the first calibration run.
SPEAKER_THETA = 0.35
# A voice check is evidence about who is speaking RIGHT NOW, so it expires.
# Re-scoring a stored clip on every turn is not verification, it is replaying
# a recording of a verification, which is what the first build did and why a
# tester could reach account data without ever being checked.
VERIFICATION_TTL_SECONDS = 300      # a check is good for five minutes
VERIFICATION_MAX_TURNS = 5          # and for at most this many turns

ANTISPOOF_LFCC_FILTERS = 20
ANTISPOOF_GMM_COMPONENTS = 8
# t-DCF cost model, used by eval/metrics.py. These are the ASVspoof 2019
# logical-access priors and costs, so the number is comparable with published
# ones. They are not free parameters: with a low target prior the C1 term goes
# negative for any non-zero verification false-accept rate and the normalised
# cost is undefined, which is a property of the cost model and not a bug.
TDCF_C_MISS = 1.0
TDCF_C_FA = 10.0
TDCF_P_TARGET = 0.9405
TDCF_P_SPOOF = 0.05
# pi_nontarget is the remainder, 0.0095, and metrics.min_tdcf derives it.

# ---------------------------------------------------------------- audio / ASR
SAMPLE_RATE = 16000
ASR_MODEL_SIZE = os.environ.get("BFSI_ASR_MODEL", "base")
ASR_COMPUTE_TYPE = os.environ.get("BFSI_ASR_COMPUTE", "int8")
ASR_DEVICE = os.environ.get("BFSI_ASR_DEVICE", "cpu")
USE_INDIC_CONFORMER = os.environ.get("BFSI_INDIC_CONFORMER", "0") == "1"  # GPU flag
VAD_THRESHOLD = 0.5
VAD_MIN_SILENCE_MS = 500
VAD_MIN_SPEECH_MS = 250

# ---------------------------------------------------------------- TTS
# Three distinct Piper voices stand in for three enrolled speakers. Enrolment
# audio is synthetic and the docs say so; /enroll accepts a real voice instead.
ENROLMENT_VOICES = ["en_US-amy-medium", "en_US-lessac-medium", "en_GB-alan-medium"]
SPOOF_VOICE = "en_US-ryan-medium"        # the attacker's cloned-voice renderer

PIPER_VOICES = {
    "en": "en_US-amy-medium",
    "hi": "hi_IN-pratham-medium",
    "mr": "hi_IN-pratham-medium",   # no Marathi Piper voice ships; documented in STACK_MAPPING
}

# ---------------------------------------------------------------- TTS engine
# Kokoro-82M is the primary voice: markedly more natural than Piper on CPU at
# a real-time factor around 0.4, which is fast enough for a live demo. Piper
# stays as the automatic fallback so a machine without the Kokoro model still
# talks. Set BFSI_TTS_ENGINE=piper to force the fallback.
TTS_ENGINE = os.environ.get("BFSI_TTS_ENGINE", "kokoro")
KOKORO_MODEL = MODEL_DIR / "kokoro" / "kokoro-v1.0.onnx"
KOKORO_VOICES_BIN = MODEL_DIR / "kokoro" / "voices-v1.0.bin"
KOKORO_VOICES = {"en": "af_heart", "hi": "hf_alpha", "mr": "hf_alpha"}
KOKORO_LANG = {"en": "en-us", "hi": "hi", "mr": "hi"}
# Slightly under 1.0 reads as measured rather than hurried. Tuned by ear on
# the demo replies; the panel hears these sentences, not a benchmark.
KOKORO_SPEED = {"en": 0.95, "hi": 0.92, "mr": 0.92}
# Piper fallback prosody. length_scale > 1 slows delivery, noise_w widens
# phoneme-duration variation, which is most of what "robotic" means.
PIPER_LENGTH_SCALE = {"en": 1.06, "hi": 1.10, "mr": 1.10}
PIPER_NOISE_SCALE = 0.667
PIPER_NOISE_W = 0.85

# ---------------------------------------------------------------- A8 ledger
LEDGER_GENESIS_HASH = "0" * 64
LEDGER_CHECKPOINT_INTERVAL = 64          # k
LEDGER_HMAC_KEY_ENV = "BFSI_LEDGER_KEY"
LEDGER_HMAC_KEY_DEFAULT = "demo-ledger-key-not-for-production"

# ---------------------------------------------------------------- crypto / auth
AES_KEY_ENV = "BFSI_AES_KEY"
AES_KEY_DEFAULT = "demo-aes-key-not-for-production"
JWT_SECRET = os.environ.get("BFSI_JWT_SECRET", "demo-jwt-secret-not-for-production")
JWT_ALG = "HS256"
JWT_TTL_SECONDS = 8 * 3600
ROLES = ["customer", "agent", "compliance_officer", "admin"]

# ---------------------------------------------------------------- consent / retention
CONSENT_PURPOSE = (
    "Handling your banking service request by voice, including speech recognition, "
    "identity verification and creating an audit record."
)
CONSENT_RETENTION_DAYS = 90
OTP_DEMO_CODE = "123456"       # SIMULATED, see capabilities.py


def _load_calibration() -> None:
    """Overlay measured values written by `make eval` / scripts/calibrate.py.

    Keeps the honesty rule: the running system uses the number that was actually
    measured, and the default above is only a cold-start placeholder.
    """
    import json
    global SIMILARITY_FLOOR_DELTA, SPEAKER_THETA
    path = RUNTIME_DIR / "calibration.json"
    if not path.exists():
        return
    try:
        cal = json.loads(path.read_text())
    except (OSError, ValueError):
        return
    SIMILARITY_FLOOR_DELTA = float(cal.get("delta", SIMILARITY_FLOOR_DELTA))
    SPEAKER_THETA = float(cal.get("theta", SPEAKER_THETA))


CALIBRATION_PATH = RUNTIME_DIR / "calibration.json"
_load_calibration()
