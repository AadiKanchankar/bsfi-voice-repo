"""R3. The call is a state machine, and the server owns it.

Two faults motivate this. The caller could speak again before the reply had
finished, which produced two overlapping voices and two replies; and once the
assistant started speaking there was no way to stop it.

Both are the same underlying problem: the client was deciding when a turn
began and ended. A browser that is already playing audio cannot arbitrate
that, because it does not know what the server is halfway through. So the
state lives here:

    CONNECTING -> GREETING -> LISTENING -> PROCESSING -> SPEAKING -> LISTENING
                                       \\-> HOLD -> AGENT
    any state  -> ENDED

The rules that follow from it:

- **Exactly one active turn per call.** `begin_turn` hands out a
  monotonically increasing `turn_id` and refuses to run two at once. The
  client plays only audio tagged with the current `turn_id` and discards
  anything stale, which is what kills the double voice.
- **New speech during PROCESSING supersedes the turn in flight.** The
  in-flight turn is cancelled rather than raced to completion, and it is
  recorded with decision `superseded` so the transcript of the call still
  accounts for it.
- **Barge-in during SPEAKING stops the reply** and records how much of it the
  caller actually heard, in milliseconds and in characters. A reply the
  caller cut off after four words was not delivered, and an audit that
  assumes it was is wrong.

Cancellation is cooperative. `CancelToken.check()` is called at every stage
boundary in `trace.stage`, so a cancelled turn stops at the next boundary
instead of running to completion and being thrown away.

State is in process, deliberately. It is the state of a live conversation on
one machine; it does not outlive the server and it should not. What must
survive is written to `calls`, `turns` and the ledger as it happens.
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field

from .security import ledger
from .trace import utcnow

CONNECTING = "CONNECTING"
GREETING = "GREETING"
LISTENING = "LISTENING"
PROCESSING = "PROCESSING"
SPEAKING = "SPEAKING"
HOLD = "HOLD"
AGENT = "AGENT"
ENDED = "ENDED"

STATES = (CONNECTING, GREETING, LISTENING, PROCESSING, SPEAKING, HOLD, AGENT, ENDED)

# Every legal move. Anything not listed raises, because a state machine that
# quietly accepts an impossible transition is a dictionary with extra steps.
ALLOWED: dict[str, set[str]] = {
    CONNECTING: {GREETING, ENDED},
    GREETING:   {LISTENING, ENDED},
    LISTENING:  {PROCESSING, ENDED},
    PROCESSING: {SPEAKING, LISTENING, HOLD, ENDED},
    SPEAKING:   {LISTENING, PROCESSING, HOLD, ENDED},
    HOLD:       {AGENT, LISTENING, ENDED},
    AGENT:      {LISTENING, HOLD, ENDED},
    ENDED:      set(),
}


class CallEnded(RuntimeError):
    """The call is over. Nothing else may happen on it."""


class TurnInFlight(RuntimeError):
    """A turn is already running and the caller asked not to supersede it."""


class Cancelled(RuntimeError):
    """Raised inside a turn that has been superseded or interrupted."""


class BadTransition(RuntimeError):
    pass


@dataclass
class CancelToken:
    """Cooperative cancellation, checked at every stage boundary."""
    reason: str | None = None
    _cancelled: bool = False

    def cancel(self, reason: str) -> None:
        self.reason, self._cancelled = reason, True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def check(self) -> None:
        if self._cancelled:
            raise Cancelled(self.reason or "cancelled")


@dataclass
class Call:
    call_id: str
    state: str = CONNECTING
    turn_id: int = -1                       # -1 until the first turn begins
    active: CancelToken | None = None       # the turn in flight, if any
    lock: threading.RLock = field(default_factory=threading.RLock)

    def snapshot(self) -> dict:
        return {"call_id": self.call_id, "state": self.state,
                "turn_id": self.turn_id if self.turn_id >= 0 else None,
                "turn_in_flight": bool(self.active and not self.active.cancelled)}


_calls: dict[str, Call] = {}
_registry_lock = threading.Lock()


def get(call_id: str) -> Call:
    with _registry_lock:
        return _calls.setdefault(call_id, Call(call_id))


def forget(call_id: str) -> None:
    """Drop in-process state for a call.

    Deliberately NOT called when a call ends. `get` recreates a missing call
    in CONNECTING, so forgetting an ended call turns "this call is over" back
    into "this call has not started", and a late or replayed request quietly
    opens a new one instead of being refused. The ENDED record is a few dozen
    bytes and it is the only thing making the refusal possible.
    """
    with _registry_lock:
        _calls.pop(call_id, None)


def reset() -> None:
    """Tests only."""
    with _registry_lock:
        _calls.clear()


# ---------------------------------------------------------------- transitions

def transition(conn: sqlite3.Connection | None, call_id: str, to: str, *,
               reason: str | None = None) -> dict:
    call = get(call_id)
    with call.lock:
        if call.state == to:
            return call.snapshot()
        if call.state == ENDED:
            raise CallEnded(f"call {call_id} has ended")
        if to not in ALLOWED[call.state]:
            raise BadTransition(f"{call.state} cannot move to {to}")
        frm, call.state = call.state, to
        if to == ENDED and conn is not None:
            conn.execute("UPDATE calls SET ended_at=?, final_state=? WHERE call_id=?",
                         (utcnow().isoformat(), reason or "ended", call_id))
            conn.commit()
        if conn is not None:
            ledger.append(conn, "call_state", {
                "call_id": call_id, "from": frm, "to": to, "reason": reason,
                "turn_id": call.turn_id if call.turn_id >= 0 else None,
            }, session_id=call_id)
        return call.snapshot()


def state(call_id: str) -> dict:
    return get(call_id).snapshot()


# ---------------------------------------------------------------- turns

def begin_turn(conn: sqlite3.Connection, call_id: str, *,
               supersede: bool = True) -> tuple[int, CancelToken]:
    """Claim the call for one turn.

    Returns the new `turn_id` and the token that turn must check. If a turn is
    already in flight it is superseded, which is the correct reading of a
    caller who has started speaking again: they are no longer waiting for the
    answer to the previous thing they said.
    """
    call = get(call_id)
    with call.lock:
        if call.state == ENDED:
            raise CallEnded(f"call {call_id} has ended")
        if call.active and not call.active.cancelled:
            if not supersede:
                raise TurnInFlight(f"turn {call.turn_id} is already running")
            _supersede(conn, call, "caller spoke again")
        if call.state in (GREETING, SPEAKING, HOLD, AGENT, CONNECTING):
            # Speaking over the assistant is a barge-in, and it is legal from
            # any of these. LISTENING is the ordinary case.
            if call.state == CONNECTING:
                transition(conn, call_id, GREETING)
                transition(conn, call_id, LISTENING)
            else:
                transition(conn, call_id, LISTENING, reason="caller spoke")
        call.turn_id += 1
        call.active = CancelToken()
        transition(conn, call_id, PROCESSING)
        return call.turn_id, call.active


def _supersede(conn: sqlite3.Connection, call: Call, reason: str) -> None:
    """Cancel the in-flight turn and leave a record that it existed."""
    assert call.active is not None
    call.active.cancel(reason)
    conn.execute(
        "INSERT OR REPLACE INTO turns (call_id, turn_id, decision, interrupted,"
        " created_at) VALUES (?,?,?,?,?)",
        (call.call_id, call.turn_id, "superseded", 1, utcnow().isoformat()))
    conn.commit()
    ledger.append(conn, "turn_superseded", {
        "call_id": call.call_id, "turn_id": call.turn_id, "reason": reason,
    }, session_id=call.call_id)


def finish_turn(conn: sqlite3.Connection, call_id: str, turn_id: int, *,
                speaking: bool = True) -> dict:
    """The turn produced a reply. Move to SPEAKING, or back to LISTENING if
    there is nothing to say."""
    call = get(call_id)
    with call.lock:
        if turn_id != call.turn_id:
            # A superseded turn finishing late must not drag the call back.
            return call.snapshot()
        call.active = None
        if call.state == ENDED:
            return call.snapshot()
        return transition(conn, call_id, SPEAKING if speaking else LISTENING)


# ---------------------------------------------------------------- controls

def interrupt(conn: sqlite3.Connection, call_id: str, *,
              played_ms: float | None = None, played_chars: int | None = None,
              reply_chars: int | None = None, source: str = "barge_in") -> dict:
    """Stop speaking. Works in every state, as the change request requires.

    How much was actually heard is recorded, not assumed. A reply the caller
    cut off after four words was not delivered, and an audit that treats it as
    delivered is wrong about what the caller was told.
    """
    call = get(call_id)
    with call.lock:
        if call.state == ENDED:
            raise CallEnded(f"call {call_id} has ended")
        was = call.state
        if call.active and not call.active.cancelled:
            call.active.cancel(source)
        delivered = None
        if reply_chars:
            delivered = round((played_chars or 0) / reply_chars, 3)
        # An interrupted read-back is not a confirmation. See
        # turn.drop_pending_for_call for why this cannot be left alone.
        from . import turn as turn_mod
        dropped = turn_mod.drop_pending_for_call(conn, call_id)
        if call.turn_id >= 0:
            # Upsert, because the turns row is written by turn.finalise at the
            # end of a turn and an interrupted turn may never get there. The
            # interruption is the fact worth keeping either way.
            conn.execute(
                "INSERT INTO turns (call_id, turn_id, interrupted, created_at)"
                " VALUES (?,?,1,?)"
                " ON CONFLICT(call_id, turn_id) DO UPDATE SET interrupted=1",
                (call_id, call.turn_id, utcnow().isoformat()))
            conn.commit()
        ledger.append(conn, "interrupted", {
            "call_id": call_id, "turn_id": call.turn_id if call.turn_id >= 0 else None,
            "from_state": was, "source": source,
            "played_ms": played_ms, "played_chars": played_chars,
            "reply_chars": reply_chars, "fraction_delivered": delivered,
            "pending_dropped": dropped,
        }, session_id=call_id)
        if was in (GREETING, SPEAKING, PROCESSING):
            transition(conn, call_id, LISTENING, reason=f"interrupted from {was}")
        return {**call.snapshot(), "interrupted_from": was,
                "fraction_delivered": delivered, "pending_dropped": dropped}


def end_call(conn: sqlite3.Connection, call_id: str, *,
             reason: str = "caller hung up") -> dict:
    """Hang up. Works in every state, including with a turn in flight."""
    call = get(call_id)
    with call.lock:
        if call.state == ENDED:
            return call.snapshot()
        if call.active and not call.active.cancelled:
            call.active.cancel("call ended")
        return transition(conn, call_id, ENDED, reason=reason)

# The recording notice is deliberately not tracked here. `calls.notice_completed`
# in the database is the authority and `recordings.call_may_record` reads it
# from there, so an interrupted greeting simply never sets it and storage keeps
# refusing. An in-process copy of that flag would be a second answer to a
# question that must have exactly one.
