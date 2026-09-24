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
from app.banking.registry import mask_mobile                         # noqa: E402
from app.config import (DATA_DIR, ENROLMENT_VOICES, PRESENTER_ID,  # noqa: E402
                        PRESENTER_MOBILE, PRESENTER_NAME, RUNTIME_DIR,
                        SAMPLE_RATE, SEED, SEED_DIR, SPOOF_VOICE)
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
        # Stored masked, the same as every customer created at runtime. The
        # seed used to write the full number, which meant two paths into one
        # column with different rules and a mobile lookup that never matched
        # a seeded customer. The full value stays in this script only, as the
        # thing a demo caller states out loud.
        conn.execute(
            "INSERT INTO customers (customer_id, name, phone, email, language, enrolled)"
            " VALUES (?,?,?,?,?,?)",
            (cid, name, mask_mobile(phone), f"{FIRST[i].lower()}.demo@example.invalid",
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


def seed_presenter(conn, rng: random.Random) -> dict:
    """One richer persona for live demos.

    Everything is synthetic, same as the generated customers. What is
    different is the depth: a salary history, a few standing payees, a real
    spread of transactions and a small investment portfolio, so a presenter
    can be asked an unscripted question and the system has something true to
    say. The presenter enrols their own voice against it through /enroll.

    The display name comes from BFSI_PRESENTER_NAME at runtime rather than
    from this file, because the repository rule is that no real personal data
    lives in it.
    """
    from datetime import datetime, timedelta, timezone
    cid, acct_id = PRESENTER_ID, "ACC9001"
    conn.execute("DELETE FROM customers WHERE customer_id=?", (cid,))
    conn.execute("DELETE FROM accounts WHERE customer_id=?", (cid,))
    conn.execute("DELETE FROM cards WHERE customer_id=?", (cid,))
    conn.execute("DELETE FROM payees WHERE customer_id=?", (cid,))
    conn.execute("DELETE FROM transactions WHERE account_id LIKE 'ACC9001%'")
    conn.execute("DELETE FROM holdings WHERE customer_id=?", (cid,))
    conn.execute("DELETE FROM sips WHERE customer_id=?", (cid,))
    conn.execute("DELETE FROM cheques WHERE account_id LIKE 'ACC9001%'")

    conn.execute(
        "INSERT INTO customers (customer_id, name, phone, email, language, enrolled)"
        " VALUES (?,?,?,?,?,?)",
        (cid, PRESENTER_NAME, mask_mobile(PRESENTER_MOBILE),
         "presenter@example.invalid", "mr", 0))
    conn.execute(
        "INSERT INTO accounts (account_id, customer_id, account_number, account_type,"
        " balance, ifsc, branch) VALUES (?,?,?,?,?,?,?)",
        (acct_id, cid, "918273645501", "savings", 214380.55, "DEMO0001234", "Nigdi"))
    conn.execute(
        "INSERT INTO accounts (account_id, customer_id, account_number, account_type,"
        " balance, ifsc, branch) VALUES (?,?,?,?,?,?,?)",
        ("ACC9002", cid, "918273645502", "current", 48210.00, "DEMO0001234", "Nigdi"))

    debit = luhn_card_ending(rng, "4321")
    credit = luhn_card_ending(rng, "9012")
    conn.execute("INSERT INTO cards (card_id, customer_id, card_number, card_type,"
                 " status, daily_limit) VALUES (?,?,?,?,?,?)",
                 ("CRD9001", cid, debit, "debit", "active", 50000.0))
    conn.execute("INSERT INTO cards (card_id, customer_id, card_number, card_type,"
                 " status, daily_limit) VALUES (?,?,?,?,?,?)",
                 ("CRD9002", cid, credit, "credit", "active", 200000.0))

    for pid, name, ifsc in [("PAY9001", "Rohan", "DEMO0001235"),
                            ("PAY9002", "Meera", "DEMO0002101"),
                            ("PAY9003", "Landlord", "DEMO0003301")]:
        conn.execute("INSERT INTO payees (payee_id, customer_id, name, account_number,"
                     " ifsc, added_at) VALUES (?,?,?,?,?,?)",
                     (pid, cid, name, f"{rng.randrange(10**11, 10**12 - 1)}", ifsc,
                      utcnow().isoformat()))

    now = datetime.now(timezone.utc)
    script = [
        (1, "credit", 78500.00, "Salary credit", "neft"),
        (2, "debit", 18000.00, "Rent to Landlord", "neft"),
        (3, "debit", 2480.50, "Grocery, Dmart Nigdi", "pos"),
        (4, "debit", 999.00, "Mobile recharge", "upi"),
        (6, "debit", 5000.00, "SIP instalment, Bluechip Fund", "netbanking"),
        (8, "debit", 1240.00, "Electricity bill", "upi"),
        (11, "debit", 3150.75, "Restaurant", "pos"),
        (13, "credit", 1830.00, "Interest credit", "netbanking"),
        (15, "debit", 22000.00, "Transfer to Rohan", "imps"),
        (18, "debit", 650.00, "Fuel", "pos"),
        (21, "debit", 14999.00, "Online purchase, electronics", "pos"),
        (25, "credit", 4200.00, "Refund, online purchase", "netbanking"),
        (28, "debit", 899.00, "Streaming subscription", "upi"),
        (31, "credit", 78500.00, "Salary credit", "neft"),
    ]
    for i, (days_ago, direction, amount, desc, channel) in enumerate(script):
        ts = (now - timedelta(days=days_ago, hours=rng.randint(0, 20))).isoformat()
        conn.execute(
            "INSERT INTO transactions (txn_id, account_id, ts, amount, direction,"
            " description, channel) VALUES (?,?,?,?,?,?,?)",
            (f"TXN9{i:03d}", acct_id, ts, amount, direction, desc, channel))

    conn.execute("INSERT INTO cheques (cheque_number, account_id, amount, status,"
                 " presented_on) VALUES (?,?,?,?,?)",
                 ("778899", acct_id, 12500.00, "cleared", (now - timedelta(days=9)).date().isoformat()))
    conn.execute("INSERT INTO cheques (cheque_number, account_id, amount, status,"
                 " presented_on) VALUES (?,?,?,?,?)",
                 ("778900", acct_id, 4000.00, "pending", (now - timedelta(days=1)).date().isoformat()))

    # Synthetic holdings. Names are invented so nothing here is a real
    # security, and the prices are made up for the same reason.
    holdings = [
        ("equity", "Demo Infotech Ltd", 120, 1280.00, 1465.30),
        ("equity", "Sample Motors Ltd", 40, 2150.00, 1980.75),
        ("equity", "Placeholder Bank Ltd", 200, 640.00, 712.40),
        ("mutual_fund", "Demo Bluechip Growth Fund", 1842.331, 54.20, 68.95),
        ("mutual_fund", "Sample Tax Saver ELSS", 910.05, 61.40, 74.10),
        ("sgb", "Sovereign Gold Bond 2031", 25, 5920.00, 7240.00),
    ]
    for i, (kind, name, units, cost, last) in enumerate(holdings):
        conn.execute(
            "INSERT INTO holdings (holding_id, customer_id, kind, name, units,"
            " avg_cost, last_price, as_of) VALUES (?,?,?,?,?,?,?,?)",
            (f"HLD9{i:03d}", cid, kind, name, units, cost, last,
             (now - timedelta(days=1)).date().isoformat()))

    conn.execute("INSERT INTO sips (sip_id, customer_id, fund, amount, day_of_month,"
                 " started_on, status) VALUES (?,?,?,?,?,?,?)",
                 ("SIP9001", cid, "Demo Bluechip Growth Fund", 5000.0, 6,
                  "2024-04-06", "active"))
    conn.execute("INSERT INTO sips (sip_id, customer_id, fund, amount, day_of_month,"
                 " started_on, status) VALUES (?,?,?,?,?,?,?)",
                 ("SIP9002", cid, "Sample Tax Saver ELSS", 2500.0, 12,
                  "2025-01-12", "active"))
    conn.commit()

    from app.banking.mock_core import MockCore
    port = MockCore(conn).portfolio_value(cid)
    return {"customer_id": cid, "name": PRESENTER_NAME, "accounts": 2, "cards": 2,
            "payees": 3, "transactions": len(script), "holdings": len(holdings),
            "sips": 2, "portfolio_value": port["value"],
            "note": "enrol a real voice against this persona through POST /enroll"}


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

    # The presenter persona gets a synthetic enrolment too, so the demo works
    # out of the box. A presenter replaces it with their own voice through
    # POST /enroll, which flips `source` to "live".
    voices = list(ENROLMENT_VOICES) + [ENROLMENT_VOICES[0]]
    ids = [f"CUST{1000 + i}" for i in range(len(ENROLMENT_VOICES))] + [PRESENTER_ID]
    for i, (voice, cid) in enumerate(zip(voices, ids)):
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

    print("1/5 synthetic banking data")
    print("   ", seed_banking(conn, rng))

    print("2/5 demo presenter persona")
    print("   ", seed_presenter(conn, rng))

    print("3/5 policy knowledge base index")
    from app.pipeline import retrieval
    print("   ", retrieval.build_index())

    print("4/5 intent head")
    from app.pipeline import nlu
    stats = nlu.train()
    print("    ", stats)

    if args.skip_voices:
        print("5/5 voices skipped")
    else:
        print("5/5 enrolled voices and anti-spoof baseline")
        print("   ", seed_voices(conn, rng))

    (RUNTIME_DIR / "seed_manifest.json").write_text(json.dumps({
        "seed": SEED, "generated_at": utcnow().isoformat(),
        "nlu": stats, "synthetic": True}, indent=2))
    print("\nseed complete. All data is synthetic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
