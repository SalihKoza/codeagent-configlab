"""C2 same-session plumbing (protocol §8, O2).

Phase 1 starts a new session with a harness-generated UUID (``--session-id <uuid>``); phase 2
continues *the same* session (``--resume <uuid>``). ``--continue`` and ``--fork-session`` are
never used. Continuity is verified from the CLI's structured output: the ``init`` and
``result`` events of both phases must report the expected UUID (readiness spike Spike A).

The final planning wrapper and approval text are NOT created here — they are placeholders whose
hashes the manifest can already represent (protocol §8 leaves the text OPEN).
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from typing import Iterable, Optional


def new_session_uuid() -> str:
    """A fresh session UUID (the harness owns session identity, not the CLI)."""
    return str(_uuid.uuid4())


@dataclass(frozen=True)
class SessionSpec:
    """How a phase attaches to a session."""

    mode: str          # "new" | "resume"
    session_id: str

    def cli_flag(self) -> tuple[str, str]:
        if self.mode == "new":
            return ("--session-id", self.session_id)
        if self.mode == "resume":
            return ("--resume", self.session_id)
        raise ValueError(f"session mode must be 'new' or 'resume', got {self.mode!r}")


def session_ids_in_events(events: Iterable[dict]) -> set[str]:
    """Collect every ``session_id`` seen in ``init``/``result`` stream-json events."""
    seen: set[str] = set()
    for e in events:
        if not isinstance(e, dict):
            continue
        etype = e.get("type")
        subtype = e.get("subtype")
        if (etype == "system" and subtype == "init") or etype == "result":
            sid = e.get("session_id")
            if isinstance(sid, str):
                seen.add(sid)
    return seen


def observed_model_in_events(events: Iterable[dict]) -> Optional[str]:
    """The Claude CLI's structured ``model`` field from its ``system``/``init`` event, if any.

    Structured field only -- never assistant/tool text, never stderr (mirrors
    :func:`session_ids_in_events`). Returns the *first* such event's model, or ``None`` if no
    init event carried one.
    """
    for e in events:
        if not isinstance(e, dict):
            continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            m = e.get("model")
            if isinstance(m, str) and m:
                return m
    return None


def verify_session_continuity(
    phase1_events: Iterable[dict], phase2_events: Iterable[dict], expected_uuid: str
) -> bool:
    """True iff both phases reported exactly the expected session UUID and nothing else.

    A mismatch means ``phase_transition_failed`` (protocol §8). The check is deliberately
    strict: each phase's init/result session ids must equal ``{expected_uuid}``.
    """
    p1 = session_ids_in_events(phase1_events)
    p2 = session_ids_in_events(phase2_events)
    return p1 == {expected_uuid} and p2 == {expected_uuid}
