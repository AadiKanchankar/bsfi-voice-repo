"""A real browser against a real stack, on its own ports and its own database.

The stack is brought up here rather than driven against whatever the presenter
has running, for two reasons: a test must not write into the demo database
five minutes before a review, and a test that silently passes because someone
forgot to start the servers is worse than no test.

Ports 8099 and 5199 are used so `make demo` on 8000 and 5173 keeps working
alongside. The database is a copy of the seeded one, so the fixtures have real
customers, accounts and a knowledge base without rebuilding them.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
API_PORT = 8099
WEB_PORT = 5199
BASE = f"http://127.0.0.1:{WEB_PORT}"


def _free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait(url: str, timeout: float = 120.0) -> bool:
    import urllib.error
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def stack(tmp_path_factory):
    src = ROOT / "runtime" / "bfsi.db"
    if not src.exists():
        pytest.skip("run `make seed` first")
    if not (ROOT / "frontend" / "node_modules").exists():
        pytest.skip("run `make setup` first")
    for port in (API_PORT, WEB_PORT):
        if not _free(port):
            pytest.skip(f"port {port} is already in use")

    workdir = tmp_path_factory.mktemp("e2e")
    db = workdir / "e2e.db"
    shutil.copy(src, db)

    env = {**os.environ, "BFSI_DB_URL": f"sqlite:///{db}",
           "BFSI_RECORDINGS_DIR": str(workdir / "recordings")}
    # start_new_session puts each server in its own process group so the
    # whole group can be signalled. `npm run dev` spawns vite as a child and
    # exits ahead of it, so terminating npm alone leaves vite holding the
    # port and the next run skips itself with "port already in use".
    api = subprocess.Popen(
        [str(ROOT / ".venv/bin/python"), "-m", "uvicorn", "app.main:app",
         "--app-dir", "backend", "--host", "127.0.0.1", "--port", str(API_PORT)],
        cwd=ROOT, env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    web = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(WEB_PORT), "--host", "127.0.0.1",
         "--strictPort"],
        cwd=ROOT / "frontend", env={**os.environ, "BFSI_API_PORT": str(API_PORT)},
        start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    try:
        if not _wait(f"http://127.0.0.1:{API_PORT}/health"):
            pytest.fail("backend did not come up on 8099")
        if not _wait(BASE):
            pytest.fail("frontend did not come up on 5199")
        yield {"base": BASE, "api": f"http://127.0.0.1:{API_PORT}", "db": db}
    finally:
        for p in (web, api):
            _stop_group(p)
        # Belt and braces: if anything still holds a port, the next run would
        # skip rather than fail, which is the worst of both.
        for port in (API_PORT, WEB_PORT):
            deadline = time.time() + 10
            while not _free(port) and time.time() < deadline:
                time.sleep(0.2)


def _stop_group(proc: subprocess.Popen) -> None:
    """Signal the server's process group, and never anyone else's.

    The obvious version of this, `os.killpg(os.getpgid(proc.pid), ...)`,
    resolves the group at teardown. If the child has already exited and
    Linux has recycled its pid, that looks up a stranger's process group and
    terminates it. Twice that stranger was the pytest run itself, which died
    at test 59 with no output and no traceback: the whole suite killed by
    its own cleanup.

    `start_new_session=True` makes the child a group leader, so its group id
    is its pid at spawn time and needs no lookup. The guard against our own
    group is belt and braces, because the failure mode is silent and the
    check is one comparison.
    """
    pgid = proc.pid                      # group leader, set at spawn
    if proc.poll() is not None:
        return                           # already gone, nothing to signal
    if pgid == os.getpgid(0):
        return                           # never signal the test runner
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)


@pytest.fixture(scope="session")
def seeded_call(stack):
    """A call with a consented recording, so playback has something to play.

    Built through the same functions the pipeline uses, not by writing rows,
    so the consent gate is exercised rather than bypassed.
    """
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    os.environ["BFSI_DB_URL"] = f"sqlite:///{stack['db']}"
    from app import db as appdb
    from app.security import recordings, speaker
    import app.security.recordings as rec_mod
    from app import turn

    rec_mod.RECORDINGS_DIR = stack["db"].parent / "recordings"
    conn = appdb.connect(stack["db"])
    s = turn.create_session(conn, "CUST1000", channel="browser")
    turn.complete_recording_notice(conn, s["session_id"], consented=True)
    clip = speaker.load_clip("CUST1000_0.wav")
    out = recordings.store(conn, s["call_id"], clip, speaker="customer", turn_id=0)
    conn.execute(
        "INSERT INTO turns (call_id, turn_id, trace_id, decision, risk_tier,"
        " language, interrupted, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (s["call_id"], 0, "e2e-trace-0", "automated", 1, "en", 0,
         "2026-09-21T10:00:00+00:00"))
    conn.commit()
    conn.close()
    return {**s, "recording_id": out["recording_id"], "customer_id": "CUST1000"}
