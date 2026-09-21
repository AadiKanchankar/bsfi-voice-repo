#!/usr/bin/env python3
"""Generate every piece of demo data, deterministically from one fixed seed.

Nothing here is real. Names are obviously fake, card numbers are Luhn valid so
the redactor is genuinely exercised, and the enrolled voices are Piper
renderings. The UI carries a banner saying so and the capability registry
marks core banking as SIMULATED.

Run: make seed
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db                                                   # noqa: E402
from app.config import (DATA_DIR, ENROLMENT_VOICES, RUNTIME_DIR, SAMPLE_RATE,  # noqa: E402
                        SEED, SEED_DIR, SPOOF_VOICE)
from app.pipeline import audio_io                                    # noqa: E402
from app.security import pii                                         # noqa: E402
from app.trace import utcnow                                         # noqa: E402

VOICE_DIR = SEED_DIR / "voices"
SPOOF_DIR = SEED_DIR / "spoofs"
TRIAL_DIR = SEED_DIR / "trials"

FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Priya", "Arjun", "Sanya",
         "Vivek", "Nisha", "Omkar", "Tara", "Yash", "Isha", "Nikhil", "Riya",
         "Sameer", "Anaya", "Dev", "Kavya"]
LAST = ["Demo", "Testwala", "Sample", "Mockre", "Fakekar", "Dummykar", "Trialkar",
        "Placeholder", "Synthetic", "Examplekar"]

BRANCHES = [
    ("DEMO0001234", "Nigdi", "Pune", "Sector 26, Pradhikaran, Nigdi, Pune 411044"),
    ("DEMO0001235", "Kothrud", "Pune", "Paud Road, Kothrud, Pune 411038"),
    ("DEMO0001236", "Hadapsar", "Pune", "Magarpatta Road, Hadapsar, Pune 411028"),
    ("DEMO0002101", "Andheri East", "Mumbai", "Chakala, Andheri East, Mumbai 400099"),
    ("DEMO0003301", "Nashik Road", "Nashik", "Jail Road, Nashik Road, Nashik 422101"),
]

DESCRIPTIONS = ["UPI payment to merchant", "Salary credit", "ATM withdrawal",
                "Electricity bill", "Mobile recharge", "Grocery purchase",
                "Insurance premium", "Interest credit", "NEFT to payee",
                "Card purchase online"]

ENROL_PHRASES = [
    "My voice is my password, and this is a demonstration account.",
    "Please confirm my account balance for the demonstration.",
    "This recording is synthetic and was generated for testing.",
]

# Held out from enrolment. Scoring a speaker against the very clips their
# enrolment mean was computed from is not a measurement, it is a tautology, and
# it reports an equal error rate of zero. These phrases produce genuine target
# trials.
TRIAL_PHRASES = [
    "I would like to check the balance on my account today.",
    "Please tell me the interest rate on a home loan.",
]


def luhn_card(rng: random.Random) -> str:
    """A Luhn-valid synthetic card number in a test BIN range."""
    partial = "4" + "".join(str(rng.randrange(10)) for _ in range(14))
    return partial + str(pii.luhn_checkdigit(partial))


# The runbook tells the presenter to say "block my card ending 4321", so one
# seeded card has to actually end in 4321 and still be Luhn valid. Searching
# for a body whose check digit lands on 1 is cheaper than hand-picking one.
DEMO_CARD_SUFFIX = "4321"


def luhn_card_ending(rng: random.Random, suffix: str = DEMO_CARD_SUFFIX) -> str:
    body_len = 15 - len(suffix)
    for _ in range(1000):
        body = "4" + "".join(str(rng.randrange(10)) for _ in range(body_len - 1))
        candidate = body + suffix[:-1]
        if pii.luhn_checkdigit(candidate) == int(suffix[-1]):
            return candidate + suffix[-1]
    raise RuntimeError("could not build a Luhn-valid card with that suffix")


def seed_banking(conn, rng: random.Random) -> dict:
    conn.executescript(
        "DELETE FROM customers; DELETE FROM accounts; DELETE FROM cards;"
        " DELETE FROM transactions; DELETE FROM payees; DELETE FROM cheques;"
        " DELETE FROM branches;")
    for ifsc, name, city, addr in BRANCHES:
        conn.execute("INSERT INTO branches (ifsc, name, city, address) VALUES (?,?,?,?)",
                     (ifsc, name, city, addr))

    n_txn = n_chq = 0
    for i in range(20):
        cid = f"CUST{1000 + i}"
        name = f"{FIRST[i]} {LAST[i % len(LAST)]}"
        phone = f"9{rng.randrange(100000000, 999999999)}"
        conn.execute(
            "INSERT INTO customers (customer_id, name, phone, email, language, enrolled)"
            " VALUES (?,?,?,?,?,?)",
            (cid, name, phone, f"{FIRST[i].lower()}.demo@example.invalid",
             rng.choice(["en", "hi", "mr"]), 1 if i < 3 else 0))

        acct_id = f"ACC{2000 + i}"
        acct_no = f"{rng.randrange(10**11, 10**12 - 1)}"
        branch = BRANCHES[i % len(BRANCHES)]
        conn.execute(
            "INSERT INTO accounts (account_id, customer_id, account_number, account_type,"
            " balance, ifsc, branch) VALUES (?,?,?,?,?,?,?)",
            (acct_id, cid, acct_no, rng.choice(["savings", "current"]),
             round(rng.uniform(5_000, 450_000), 2), branch[0], branch[1]))

        for j in range(rng.randint(1, 2)):
            # The first customer's debit card is the one the demo script names.
            number = (luhn_card_ending(rng) if (i == 0 and j == 0) else luhn_card(rng))
            conn.execute(
                "INSERT INTO cards (card_id, customer_id, card_number, card_type, status,"
                " daily_limit) VALUES (?,?,?,?,?,?)",
                (f"CRD{3000 + i * 2 + j}", cid, number,
                 "debit" if j == 0 else "credit", "active",
                 float(rng.choice([25_000, 50_000, 100_000]))))

        base = utcnow()
        for k in range(rng.randint(8, 15)):
            ts = base.replace(microsecond=0).timestamp() - k * rng.randint(3600, 86400)
            from datetime import datetime, timezone
            conn.execute(
                "INSERT INTO transactions (txn_id, account_id, ts, amount, direction,"
                " description, channel) VALUES (?,?,?,?,?,?,?)",
                (f"TXN{i:02d}{k:03d}", acct_id,
                 datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                 round(rng.uniform(100, 45_000), 2),
                 rng.choice(["debit", "credit"]), rng.choice(DESCRIPTIONS),
                 rng.choice(["upi", "atm", "netbanking", "pos"])))
            n_txn += 1

        for p in range(rng.randint(1, 3)):
            pname = FIRST[(i + p + 1) % len(FIRST)]
            conn.execute(
                "INSERT INTO payees (payee_id, customer_id, name, account_number, ifsc, added_at)"
                " VALUES (?,?,?,?,?,?)",
                (f"PAY{i:02d}{p}", cid, pname, f"{rng.randrange(10**11, 10**12 - 1)}",
                 BRANCHES[(i + p) % len(BRANCHES)][0], utcnow().isoformat()))

        for c in range(rng.randint(0, 2)):
            conn.execute(
                "INSERT INTO cheques (cheque_number, account_id, amount, status, presented_on)"
                " VALUES (?,?,?,?,?)",
                (f"{456780 + i * 3 + c}", acct_id, round(rng.uniform(1_000, 90_000), 2),
                 rng.choice(["cleared", "pending", "returned for insufficient funds"]),
                 utcnow().isoformat()[:10]))
            n_chq += 1
    conn.commit()
    return {"customers": 20, "branches": len(BRANCHES), "transactions": n_txn,
            "cheques": n_chq}


def _channel(audio: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Simulate a telephony channel: band limit, mild noise, gain wobble.

    Bona fide clips go through this and spoof clips do not, which models the
    difference between a customer on a call and a clean synthetic injection.
    The honesty caveat is in docs/RESULTS.md: both classes originate from a TTS
    system, so the measured numbers characterise these two conditions and not
    human speech against deepfakes.
    """
    from scipy.signal import butter, lfilter
    b, a = butter(4, [300 / (SAMPLE_RATE / 2), 3400 / (SAMPLE_RATE / 2)], btype="band")
    out = lfilter(b, a, audio).astype(np.float32)
    out += rng.normal(0, 0.002, size=out.shape).astype(np.float32)
    return (out * float(rng.uniform(0.7, 1.0))).astype(np.float32)


def _render(voice: str, phrase: str) -> bytes:
    """Render one phrase with a named Piper voice. WAV bytes, nothing cached."""
    import io
    import wave

    from piper import PiperVoice

    from app.pipeline.tts import VOICE_DIR as PIPER_DIR
    key = (voice,)
    v = _RENDER_CACHE.get(key)
    if v is None:
        v = PiperVoice.load(str(PIPER_DIR / f"{voice}.onnx"),
                            config_path=str(PIPER_DIR / f"{voice}.onnx.json"))
        _RENDER_CACHE[key] = v
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        v.synthesize_wav(phrase, wf)
    return buf.getvalue()


_RENDER_CACHE: dict = {}


def seed_voices(conn, rng: random.Random) -> dict:
    """Three enrolled speakers plus a spoof set, all rendered with Piper.

    Enrolment audio is synthetic. That is stated here, in the capability
    registry, in RESULTS.md and on the dashboard. A team member who wants their
    own voice in the live demo enrols it through POST /enroll, which overwrites
    the synthetic embedding and flips the source field to 'live'.
    """
    from app.security import antispoof, speaker

    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    SPOOF_DIR.mkdir(parents=True, exist_ok=True)
    TRIAL_DIR.mkdir(parents=True, exist_ok=True)
    nprng = np.random.default_rng(SEED)
    n_trials = 0

    bona: list[bytes] = []
    spoofs: list[bytes] = []
    enrolled: list[str] = []

    for i, voice in enumerate(ENROLMENT_VOICES):
        cid = f"CUST{1000 + i}"
        clips: list[bytes] = []
        try:
            for j, phrase in enumerate(ENROL_PHRASES):
                audio = _channel(audio_io.decode(_render(voice, phrase)), nprng)
                wav = audio_io.to_wav_bytes(audio)
                (VOICE_DIR / f"{cid}_{j}.wav").write_bytes(wav)
                clips.append(wav)
                bona.append(wav)
        except Exception as exc:                          # noqa: BLE001
            return {"enrolled": len(enrolled), "error": f"voice {voice}: {exc}"}
        speaker.enrol(conn, cid, clips, source="synthetic")
        enrolled.append(cid)

        # Held-out trial clips, same speaker, phrases the enrolment never saw.
        try:
            for j, phrase in enumerate(TRIAL_PHRASES):
                audio = _channel(audio_io.decode(_render(voice, phrase)), nprng)
                (TRIAL_DIR / f"{cid}_trial_{j}.wav").write_bytes(audio_io.to_wav_bytes(audio))
                n_trials += 1
        except Exception as exc:                          # noqa: BLE001
            print(f"  trial clips for {voice} unavailable: {exc}")

        # The spoof set: the same phrases rendered by a different voice,
        # modelling a cloned-voice injection rather than a replay.
        #
        # The spoof clips go through the same simulated channel as the bona
        # fide ones, and that is not a detail. When only the bona fide clips
        # were band-limited, the GMM learned "wideband means spoof" and scored
        # a clean recording of the enrolled speaker at 0.02. It was a bandwidth
        # detector wearing a countermeasure's name. Sharing the channel forces
        # it onto voice and vocoder cues, which is the thing being claimed.
        try:
            for j, phrase in enumerate(ENROL_PHRASES):
                audio = _channel(audio_io.decode(_render(SPOOF_VOICE, phrase)), nprng)
                data = audio_io.to_wav_bytes(audio)
                (SPOOF_DIR / f"{cid}_spoof_{j}.wav").write_bytes(data)
                spoofs.append(data)
        except Exception as exc:                          # noqa: BLE001
            print(f"  spoof voice unavailable: {exc}")

    trained = antispoof.train(bona, spoofs) if (bona and spoofs) else {}
    return {"enrolled": len(enrolled), "customers": enrolled,
            "bona_clips": len(bona), "spoof_clips": len(spoofs),
            "trial_clips": n_trials, "antispoof": trained}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-voices", action="store_true",
                    help="skip Piper rendering and speaker enrolment")
    args = ap.parse_args()

    rng = random.Random(SEED)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    conn = db.init_db()

    print("1/4 synthetic banking data")
    print("   ", seed_banking(conn, rng))

    print("2/4 policy knowledge base index")
    from app.pipeline import retrieval
    print("   ", retrieval.build_index())

    print("3/4 intent head")
    from app.pipeline import nlu
    stats = nlu.train()
    print("    ", stats)

    if args.skip_voices:
        print("4/4 voices skipped")
    else:
        print("4/4 enrolled voices and anti-spoof baseline")
        print("   ", seed_voices(conn, rng))

    (RUNTIME_DIR / "seed_manifest.json").write_text(json.dumps({
        "seed": SEED, "generated_at": utcnow().isoformat(),
        "nlu": stats, "synthetic": True}, indent=2))
    print("\nseed complete. All data is synthetic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
