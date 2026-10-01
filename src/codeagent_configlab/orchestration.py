"""Per-configuration agent execution: C0/C1 = one invocation, C2 = planning + implementation (G2).

Terminology kept distinct on purpose: one *run* (experimental unit, one ``result.json``) contains
one Claude CLI *invocation* for C0/C1 and two for C2 (*phase 1* planning, *phase 2*
implementation). Two C2 invocations are never two runs.

C2 contract (protocol §8, readiness spike A/B/C), wired from existing primitives only:

* phase 1: :func:`~codeagent_configlab.envelope.planning_envelope` (read-only tool set + ``ro``
  outer sandbox), ``--session-id <uuid>``, input = the frozen planning wrapper with the task
  statement inserted unmodified;
* between phases, nothing is sent except the frozen approval message; the plan is never read by
  a human;
* phase 2: the **same** implementation envelope object as C0/C1, ``--resume <uuid>``;
* one wall-clock budget (G1 :class:`Deadline`) for both phases; phase 2 receives what phase 1
  left, measured at the end of phase 1, so the harness's inter-phase checks are not charged
  (``docs/PILOT_PLAN.md`` §9).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .envelope import ExecutionEnvelope, implementation_envelope, planning_envelope
from .hashing import sha256_file
from .lifecycle import AgentRunOutcome  # lifecycle imports this module lazily (no cycle)
from .process_control import Deadline
from .session import SessionSpec, session_ids_in_events, verify_session_continuity
from .status import AgentOutcome, C2Protocol
from .treatment import Treatment

# Phase-1 read-only check: everything in the working copy is hashed -- including .git,
# node_modules and the seeded .claude settings -- except this one generated-cache directory.
PHASE1_IGNORED_DIRS = ("__pycache__",)

_INFRA = (AgentOutcome.AUTH_FAILURE, AgentOutcome.LIMIT_INTERRUPTED, AgentOutcome.HARNESS_ERROR)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_tree(root: Path, ignore_dirs: tuple[str, ...] = PHASE1_IGNORED_DIRS) -> dict[str, str]:
    """Relative path -> content hash (symlinks recorded by target, never followed)."""
    out: dict[str, str] = {}
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        for name in filenames:
            f = Path(dirpath) / name
            rel = f.relative_to(root).as_posix()
            if f.is_symlink():
                out[rel] = "symlink:" + os.readlink(f)
            else:
                out[rel] = sha256_file(f)
    return out


def verify_phase1_readonly(working_copy: Path, before: dict[str, str], home: Path,
                           session_uuid: str) -> dict:
    """Did phase 1 leave the repository and Claude-loadable state untouched?

    Three checks, all narrow and explicit:

    1. working-copy snapshot after == before (only ``__pycache__`` excluded);
    2. ``~/.claude/projects/<slug>/`` holds nothing but ``<uuid>.jsonl`` and an empty ``memory/``
       (the residual write channel found in readiness spike B: phase 2 would load that memory);
    3. no user-level instruction material appeared (re-run of the preflight check).
    """
    from .preflight import PreflightContext, _project_slug, check_user_level_instructions
    from .status import Preflight

    after = snapshot_tree(working_copy)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))

    project_extra: list[str] = []
    proj = Path(home) / ".claude" / "projects" / _project_slug(Path(working_copy))
    if proj.is_dir():
        for entry in proj.iterdir():
            if entry.name == f"{session_uuid}.jsonl" and entry.is_file():
                continue
            if entry.name == "memory" and entry.is_dir() and not any(entry.iterdir()):
                continue
            project_extra.append(entry.name)

    user = check_user_level_instructions(PreflightContext(working_copy=Path(working_copy), home=Path(home)))
    user_level = user.detail if user.status is Preflight.FAILED else None

    return {
        "ok": not changed and not project_extra and user_level is None,
        "changed_paths": changed,
        "project_state_extra": sorted(project_extra),
        "user_level_instructions": user_level,
        "ignored_dirs": list(PHASE1_IGNORED_DIRS),
    }


@dataclass
class PhaseRecord:
    """One Claude CLI invocation inside a run."""

    label: str                  # "single" (C0/C1) | "phase1" | "phase2"
    envelope_phase: str         # "implementation" | "planning"
    envelope_hash: str
    session_flag: str           # "--session-id" | "--resume"
    expected_session_id: str
    budget_seconds: Optional[float]   # budget handed to this invocation (None = no shared cap)
    started_at: str
    ended_at: str
    duration_seconds: float
    outcome: AgentRunOutcome
    observed_session_ids: list[str] = field(default_factory=list)
    session_ok: bool = False
    observed_model: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "envelope_phase": self.envelope_phase,
            "envelope_hash": self.envelope_hash,
            "session_flag": self.session_flag,
            "expected_session_id": self.expected_session_id,
            "observed_session_ids": self.observed_session_ids,
            "session_ok": self.session_ok,
            "observed_model": self.observed_model,
            "budget_seconds": self.budget_seconds,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "exit_code": self.outcome.exit_code,
            "agent_outcome": self.outcome.agent_outcome.value,
            "detail": self.outcome.detail,
            "process": self.outcome.process,
        }


@dataclass
class ConditionResult:
    outcome: AgentRunOutcome                 # the run-level (overall) agent outcome
    phases: list[PhaseRecord]
    c2_protocol: C2Protocol = C2Protocol.NOT_APPLICABLE
    c2_detail: str = ""
    readonly: Optional[dict] = None
    gap_seconds: Optional[float] = None
    plan_text: Optional[str] = None

    def c2_record(self) -> dict:
        return {
            "invocations": len(self.phases),
            "phases": [p.to_dict() for p in self.phases],
            "c2_protocol": self.c2_protocol.value,
            "c2_detail": self.c2_detail,
            "phase1_readonly": self.readonly,
            "inter_phase_gap_seconds": self.gap_seconds,
            "session_continuity_verified": self.outcome.session_continuity_verified,
        }


def _plan_text(events: list[dict]) -> Optional[str]:
    for e in reversed(events):
        if isinstance(e, dict) and e.get("type") == "result" and isinstance(e.get("result"), str):
            return e["result"]
    return None


def run_agent_condition(
    *,
    configuration: str,
    runner,
    working_copy,
    envelope: ExecutionEnvelope,
    session_uuid: str,
    home: Path,
    task_statement: Optional[str] = None,
    treatment: Optional[Treatment] = None,
    budget_seconds: Optional[float] = None,
    clock: Callable[[], float] = None,
) -> ConditionResult:
    """Execute the agent part of one run for ``configuration``. Never retries anything."""
    import time

    clock = clock or time.monotonic
    wc_path = Path(working_copy.path)

    # Implementation-envelope invariant: C0 == C1 == C2 phase 2, all built the same way.
    if envelope != implementation_envelope(configuration, envelope.security_policy):
        bad = AgentRunOutcome(exit_code=None, session_id=None, agent_outcome=AgentOutcome.HARNESS_ERROR,
                              detail="implementation envelope differs from implementation_envelope()")
        return ConditionResult(outcome=bad, phases=[])

    shared = Deadline.start(budget_seconds, clock=clock) if budget_seconds is not None else None

    def invoke(label, env, spec, prompt, deadline, pass_deadline) -> PhaseRecord:
        kwargs = {}
        if prompt is not None:
            kwargs["prompt"] = prompt
        if pass_deadline:
            kwargs["deadline"] = deadline
        started, t0 = _utc_now(), clock()
        out = runner.run(working_copy, env, spec, **kwargs)
        rec = PhaseRecord(
            label=label, envelope_phase=env.phase, envelope_hash=env.envelope_hash(),
            session_flag=spec.cli_flag()[0], expected_session_id=session_uuid,
            budget_seconds=deadline.budget_seconds if deadline is not None else None,
            started_at=started, ended_at=_utc_now(), duration_seconds=round(clock() - t0, 6),
            outcome=out,
        )
        ids = session_ids_in_events(out.events)
        rec.observed_session_ids = sorted(ids)
        rec.observed_model = out.observed_model
        # A phase that finished normally must report exactly the expected session; one that was
        # cut short (cap, infra) may have reported nothing yet, but never a foreign id.
        rec.session_ok = (ids == {session_uuid}) if out.agent_outcome is AgentOutcome.COMPLETED \
            else ids <= {session_uuid}
        return rec

    # ---- C0 / C1: one implementation invocation ------------------------------------------
    if configuration in ("C0", "C1"):
        rec = invoke("single", envelope, SessionSpec("new", session_uuid), task_statement,
                     shared, pass_deadline=shared is not None)
        return ConditionResult(outcome=rec.outcome, phases=[rec])

    # ---- C2: planning -> fixed approval -> implementation in the same session -------------
    if configuration != "C2":
        raise ValueError(f"configuration must be C0/C1/C2, got {configuration!r}")
    plan_env = planning_envelope(envelope.security_policy)
    before = snapshot_tree(wc_path)
    # C2 always passes its deadline explicitly (None = uncapped) so no phase ever falls back to a
    # full per-invocation timeout of its own.
    p1 = invoke("phase1", plan_env, SessionSpec("new", session_uuid),
                treatment.render_planning_prompt(task_statement), shared, pass_deadline=True)
    remaining = shared.remaining() if shared is not None else None
    gap_t0 = clock()
    readonly = verify_phase1_readonly(wc_path, before, Path(home), session_uuid)
    result = ConditionResult(outcome=p1.outcome, phases=[p1], c2_protocol=C2Protocol.OK,
                             readonly=readonly, plan_text=_plan_text(p1.outcome.events))

    def finish(outcome: AgentRunOutcome, **changes) -> ConditionResult:
        continuity = len(result.phases) == 2 and verify_session_continuity(
            result.phases[0].outcome.events, result.phases[1].outcome.events, session_uuid)
        result.outcome = replace(
            outcome,
            phase1_exit_code=result.phases[0].outcome.exit_code,
            phase2_exit_code=result.phases[1].outcome.exit_code if len(result.phases) == 2 else None,
            session_continuity_verified=continuity,
            **changes,
        )
        return result

    if not readonly["ok"]:
        result.c2_protocol = C2Protocol.PHASE1_WRITE
        result.c2_detail = "phase 1 changed state it must not change; phase 2 not started"
        return finish(p1.outcome)
    if not p1.session_ok:
        result.c2_protocol = C2Protocol.PHASE_TRANSITION_FAILED
        result.c2_detail = f"phase 1 reported session(s) {p1.observed_session_ids}, expected {session_uuid}"
        return finish(p1.outcome)
    if p1.outcome.agent_outcome is not AgentOutcome.COMPLETED:
        # timeout (valid), error_exit (valid; the run cannot continue, protocol §4) or an
        # infrastructure class -- in every case phase 2 is not started and nothing is faked.
        result.c2_detail = f"phase 1 ended as {p1.outcome.agent_outcome.value}; phase 2 not started"
        return finish(p1.outcome)
    if remaining is not None and remaining <= 0:
        result.c2_detail = "shared budget exhausted at the end of phase 1; phase 2 not started"
        return finish(p1.outcome, agent_outcome=AgentOutcome.TIMEOUT,
                      detail="wall-clock cap reached at the end of phase 1")

    phase2_deadline = Deadline.start(remaining, clock=clock) if remaining is not None else None
    result.gap_seconds = round(clock() - gap_t0, 6)
    p2 = invoke("phase2", envelope, SessionSpec("resume", session_uuid),
                treatment.approval_message, phase2_deadline, pass_deadline=True)
    result.phases.append(p2)
    if not p2.session_ok:
        result.c2_protocol = C2Protocol.PHASE_TRANSITION_FAILED
        result.c2_detail = f"phase 2 reported session(s) {p2.observed_session_ids}, expected {session_uuid}"
    return finish(p2.outcome)
