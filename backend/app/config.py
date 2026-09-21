"""Every tunable number in the system lives here.

Rule for this file: if a value influences a decision the compliance dashboard
shows, it is named here and nowhere else. No magic numbers inline in the
pipeline. The docs in docs/ALGORITHMS.md cite these names directly.
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Read .env before anything else looks at the environment.

    The CLU provider key lives here rather than in a shell profile so it is
    one gitignored file to manage. Parsed by hand: no dependency, and it
    cannot execute anything the way `source .env` can.
    """
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        # Real environment wins, so `BFSI_CLU_PROVIDER=x make demo` still works.
        os.environ.setdefault(key, value)


_load_dotenv()

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
    # Investment handling, split deliberately into two intents.
    #
    # investment_info is factual and answerable: what a demat account is, what
    # the bank's fixed deposit rates are, what the lock-in on an ELSS fund is,
    # what a customer's own holdings are worth.
    #
    # investment_advice is "which stock should I buy", "is this a good time to
    # invest", "should I switch funds". Under the SEBI (Investment Advisers)
    # Regulations 2013, advice of that kind may only be given by a registered
    # investment adviser, and an automated assistant is not one. So it is a
    # mandatory human handover, in the same class as a fraud report, and no
    # amount of model confidence can automate it. A bank that let a voice bot
    # answer it would have a bigger problem than a bad answer.
    "investment_info", "investment_advice",
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
                     "investment_info", "investment_advice", "out_of_scope"}
GROUNDED_INTENTS = {"product_info", "apply_loan"}

# ---------------------------------------------------------------- CLU layer
# Contextual Language Understanding: an optional model that reads a turn and
# returns structured meaning. It sits between ASR and the deterministic
# pipeline and it is NOT a decision maker. Risk, authentication, retrieval
# grounding and the automation gate are untouched by it and remain
# authoritative. See docs/CLU.md.
#
# Default is "null", so a fresh clone behaves exactly like the frozen
# snapshot until someone opts in.
CLU_PROVIDER = os.environ.get("BFSI_CLU_PROVIDER", "null")
# Never logged, never traced, never in an error message. providers.py reads
# it by name from the environment and does not carry it in any object.
# Groq's free tier retires models regularly: llama-3.3-70b-versatile was the
# default here and is already gone. If a call fails, `make clu-models` lists
# what the endpoint actually serves today. Measured on the code-mixed cases,
# qwen3.8-27b was both the most accurate and the fastest of what is offered.
CLU_MODEL = os.environ.get("BFSI_CLU_MODEL", "qwen/qwen3.8-27b")
CLU_TEMPERATURE = float(os.environ.get("BFSI_CLU_TEMPERATURE", "0"))
CLU_MAX_TOKENS = int(os.environ.get("BFSI_CLU_MAX_TOKENS", "400"))
CLU_TIMEOUT_S = float(os.environ.get("BFSI_CLU_TIMEOUT", "12"))
# Free tiers cap input tokens per minute, not just requests. Groq's is 7000
# ITPM, which at this prompt size is about fourteen calls a minute. A 429 is
# a wait instruction, not a failure, so it is retried rather than dropped.
CLU_MAX_RETRIES = int(os.environ.get("BFSI_CLU_MAX_RETRIES", "3"))
CLU_MAX_BACKOFF_S = float(os.environ.get("BFSI_CLU_MAX_BACKOFF", "30"))
LLM_API_BASE = os.environ.get("BFSI_LLM_API_BASE", "https://api.groq.com/openai/v1")
LLM_API_KEY_ENV = "BFSI_LLM_API_KEY"

# Routing. The model is not called on every turn: most turns are a confident,
# monolingual, single-intent request that the logistic head already gets
# right, and calling out for those costs latency and money for nothing.
CLU_CALL_BELOW_CONFIDENCE = 0.70   # baseline intent posterior under this
CLU_CALL_BELOW_MARGIN = 0.15       # or top two intents this close together
CLU_CALL_ON_CODE_MIX = True        # or the utterance mixes languages
CLU_CALL_ON_FOLLOWUP = True        # or it looks like a follow-up to the last turn
# Or it coordinates two asks. A single-label head cannot represent "balance
# and also the IFSC", and it can be perfectly confident about whichever half
# it picked, so neither the confidence nor the margin trigger fires. Both
# compound failures left after the first evaluation run were this.
CLU_CALL_ON_COMPOUND = True
CLU_COMPOUND_MIN_WORDS = 6
CLU_CONTEXT_TURNS = 4              # bounded history sent to the model

# Safety floor. The CLU may RAISE the assessed risk of a turn and may never
# lower it: if either the deterministic head or the CLU reads an utterance as
# fraud, dispute or an agent request, that reading wins. A language model
# cannot talk this system down a tier.
CLU_MAY_LOWER_RISK = False
# ...with one carve-out, because an absolute rule was worse in testing. The
# deterministic head fired `fraud_report` at 0.30 confidence on the harmless
# follow-up "aur uske pehle wali?", and an unconditional floor then pinned
# that turn to mandatory handover. A 0.30 posterior is noise, not evidence of
# fraud. So a downgrade from a hard-handover intent is refused UNLESS the
# deterministic reading was itself unconfident AND the language layer is
# confident. Both conditions, and the trace records every time it happens.
CLU_BASELINE_TRUSTED_ABOVE = 0.45   # below this the head is not evidence
CLU_OVERRIDE_NEEDS_CONFIDENCE = 0.70  # and the CLU has to be sure to take over

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
    "investment_info": 0.30,
    "investment_advice": 1.00,
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
    "investment_advice": 3,
    "investment_info": 1,        # holdings are account data
}

TIER_CUTPOINTS = (0.25, 0.50, 0.75)      # t1, t2, t3
TIER_TAU = (0.50, 0.62, 0.75, 1.01)      # tier 3 tau is unreachable by design
# These three bypass the score entirely. A scoring bug must never automate them.
HARD_TIER3_INTENTS = {"fraud_report", "dispute_txn", "agent_request",
                      "investment_advice"}
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

# Not every tier 3 is a risk signal. A fraud report or a dispute says the
# account may be compromised, so the rest of the call stays elevated. Asking
# to speak to a human, or asking for investment advice, says nothing about
# risk at all: it is simply outside what the assistant may answer. Those
# escalate the turn and leave the session where it was, otherwise asking
# about stocks locks you out of your own balance for the rest of the call.
NON_RATCHETING_TIER3 = {"agent_request", "investment_advice"}

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

# ---------------------------------------------------------------- presenter
# The demo persona. Synthetic like everything else, but with a fuller history
# than the generated customers so a live demo has something to talk about,
# and set aside for whoever is presenting to enrol their own voice into.
#
# Set BFSI_PRESENTER_NAME locally if you want your own name on screen. It is
# read from the environment rather than committed, because the repository
# rule is that no real personal data lives in it, and a name is personal data.
PRESENTER_ID = "CUST9001"
PRESENTER_NAME = os.environ.get("BFSI_PRESENTER_NAME", "Demo Presenter")

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

# ---------------------------------------------------------------- TTS
# Engine order: elevenlabs if a key is set, else kokoro, else piper. Each
# falls through to the next rather than going silent mid-demo.
TTS_ENGINE = os.environ.get("BFSI_TTS_ENGINE", "auto")   # auto|elevenlabs|kokoro|piper

# One knob, honoured by every engine and every language. Before this existed,
# Piper spoke Hindi with hi_IN-pratham (male) while Kokoro spoke it with
# hf_alpha (female), so the gender flipped depending on which engine ran.
TTS_GENDER = os.environ.get("BFSI_TTS_GENDER", "female")  # female|male

# Indian-accented English comes from a Hindi Kokoro voice reading English
# with the ENGLISH phonemiser. Measured: voice hf_alpha with lang en-us gives
# an Indian accent at the same round-trip WER as the American voice (0.286),
# while lang hi on English text mangles the words (0.43 to 0.48). Set
# BFSI_TTS_ACCENT=neutral for the American voices instead.
TTS_ACCENT = os.environ.get("BFSI_TTS_ACCENT", "indian")  # indian|neutral

KOKORO_MODEL = MODEL_DIR / "kokoro" / "kokoro-v1.0.onnx"
KOKORO_VOICES_BIN = MODEL_DIR / "kokoro" / "voices-v1.0.bin"
# (accent, gender) -> voice, per language.
KOKORO_VOICE_TABLE = {
    "en": {("indian", "female"): "hf_alpha", ("indian", "male"): "hm_omega",
           ("neutral", "female"): "af_heart", ("neutral", "male"): "am_michael"},
    "hi": {("indian", "female"): "hf_alpha", ("indian", "male"): "hm_omega",
           ("neutral", "female"): "hf_alpha", ("neutral", "male"): "hm_omega"},
    "mr": {("indian", "female"): "hf_beta", ("indian", "male"): "hm_psi",
           ("neutral", "female"): "hf_beta", ("neutral", "male"): "hm_psi"},
}
# The phonemiser, which is NOT the same as the voice. English text always
# goes through the English phonemiser even when spoken by a Hindi voice.
KOKORO_LANG = {"en": "en-us", "hi": "hi", "mr": "hi"}
KOKORO_SPEED = {"en": 0.95, "hi": 0.92, "mr": 0.92}

PIPER_VOICES = {
    "en": {"female": "en_US-amy-medium", "male": "en_US-ryan-medium"},
    "hi": {"female": "hi_IN-pratham-medium", "male": "hi_IN-pratham-medium"},
    "mr": {"female": "hi_IN-pratham-medium", "male": "hi_IN-pratham-medium"},
}
# Piper ships no female Hindi voice in the set we download, so the fallback
# cannot honour TTS_GENDER for Hindi or Marathi. capabilities.py says so.
PIPER_LENGTH_SCALE = {"en": 1.06, "hi": 1.10, "mr": 1.10}
PIPER_NOISE_SCALE = 0.667
PIPER_NOISE_W = 0.85

# ElevenLabs, optional. Sends the REPLY TEXT to a third party, and a reply can
# contain a balance or an account's last four, so this is customer data
# leaving the machine and the trace records it per turn.
ELEVENLABS_KEY_ENV = "BFSI_ELEVENLABS_API_KEY"
ELEVENLABS_MODEL = os.environ.get("BFSI_ELEVENLABS_MODEL", "eleven_turbo_v2_5")
ELEVENLABS_VOICES = {
    # Indian-English voices from the public library. Override per language.
    "en": os.environ.get("BFSI_ELEVENLABS_VOICE_EN", "mActWQg9kibLro8zUvjW"),
    "hi": os.environ.get("BFSI_ELEVENLABS_VOICE_HI", "mActWQg9kibLro8zUvjW"),
    "mr": os.environ.get("BFSI_ELEVENLABS_VOICE_MR", "mActWQg9kibLro8zUvjW"),
}

# Prosody. Off makes every engine read a reply as one unbroken block.
TTS_NATURAL_PAUSES = os.environ.get("BFSI_TTS_PAUSES", "1") == "1"
TTS_BREATHS = os.environ.get("BFSI_TTS_BREATHS", "1") == "1"

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
