#!/usr/bin/env python3
"""Beat 10. Corrupt one stored ledger record with raw SQL, the way a rogue DBA
or a compromised host would, and let the dashboard catch it.

This touches only the `payload` column. It does not recompute any hash, which
is exactly what makes it detectable: the record's stored hash no longer matches
its own contents.

    python scripts/tamper_demo.py            corrupt a middle record
    python scripts/tamper_demo.py --index 5  corrupt a specific one
    python scripts/tamper_demo.py --restore  put it back
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db                        # noqa: E402
from app.config import RUNTIME_DIR        # noqa: E402
from app.security import ledger           # noqa: E402

BACKUP = RUNTIME_DIR / "tamper_backup.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=None)
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--field", default="decision",
                    help="field inside the payload JSON to rewrite")
    ap.add_argument("--value", default="automated")
    args = ap.parse_args()

    conn = db.init_db()

    if args.restore:
        if not BACKUP.exists():
            print("nothing to restore")
            return 1
        saved = json.loads(BACKUP.read_text())
        conn.execute("UPDATE ledger SET payload=? WHERE idx=?",
                     (saved["payload"], saved["idx"]))
        conn.commit()
        BACKUP.unlink()
        out = ledger.verify(conn)
        print(f"restored record {saved['idx']}; chain ok = {out['ok']}")
        return 0

    total = conn.execute("SELECT COUNT(*) c FROM ledger").fetchone()["c"]
    if total == 0:
        print("the ledger is empty; run the demo first so there is something to tamper with")
        return 1
    idx = args.index if args.index is not None else total // 2
    row = conn.execute("SELECT * FROM ledger WHERE idx=?", (idx,)).fetchone()
    if not row:
        print(f"no record at index {idx}")
        return 1

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps({"idx": idx, "payload": row["payload"]}))

    payload = json.loads(row["payload"])
    before = payload.get(args.field)
    payload[args.field] = args.value
    # Deliberately not canonical_json: a real tamper does not care about our
    # serialisation rules. The chain catches it either way.
    conn.execute("UPDATE ledger SET payload=? WHERE idx=?",
                 (json.dumps(payload, sort_keys=True, separators=(",", ":")), idx))
    conn.commit()

    print(f"tampered with ledger record {idx} ({row['record_id']})")
    print(f"  field {args.field!r}: {before!r} -> {args.value!r}")
    out = ledger.verify(conn)
    print(f"\nverification now says:")
    print(f"  ok                 {out['ok']}")
    print(f"  first broken index {out['first_broken_index']}")
    print(f"  broken record id   {out['broken_record_id']}")
    print(f"  failed check       {out.get('broken_check')}")
    print(f"  records checked    {out['records_checked']} of {out.get('total_records')}")
    print("\nOpen the compliance dashboard and click Verify Ledger.")
    print("Run with --restore to put the record back.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
