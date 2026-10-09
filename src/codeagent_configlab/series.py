"""Pilot-series execution layer (G10): planned cells, attempts, schedule, replacement linkage.

Concepts (``docs/PILOT_SERIES_V0.md``):

* **planned cell** -- one intended observation ``task x configuration x repetition``; its
  ``cell_id`` is derived from the frozen specification only;
* **attempt** -- one execution of the single-run lifecycle for a cell; ``run_id`` is the opaque
  attempt id. Attempt 1 is the original; at most ``max_replacements_per_cell`` (frozen: 1,
  PILOT_PLAN §11) replacement attempts follow, only after an explicit operator approval of a
  replacement-eligible class. A replacement is never a new cell or repetition;
* **re-evaluation** -- the evaluator re-run on an attempt's preserved final working copy
  (``evaluation_pending``, PILOT_PLAN §10 / G8). It never starts a new agent attempt.

State lives in an append-only ``events.jsonl`` under the series root (outside every agent-visible
path); cell states are *derived* from it, never stored separately. One attempt per driver call; a
``attempt_started`` without a matching end is ``ambiguous`` and blocks execution until
:meth:`Series.recover` resolves it -- an attempt id is never executed twice.

The driver orchestrates :class:`~codeagent_configlab.lifecycle.RunLifecycle`; it does not
duplicate lifecycle logic. The run budget and model come only from the frozen manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .envelope import (IMPLEMENTATION_TOOLS, PLANNING_TOOLS, SecurityPolicy,
                       implementation_envelope, planning_envelope)
from .hashing import canonical_json_hash
from .ids import new_run_id, new_workspace_token
from .manifest import (CLAUDE_CODE_VERSION, NODE_VERSION, NPM_VERSION, SANDBOX_RUNTIME_VERSION,
                       RunManifest)
from .sentinels import OPEN
from .status import AnalysisEligibility as AE
from .task_package import TaskPackage
from .treatment import Treatment

NAMESPACE_PILOT = "PILOT"
NAMESPACE_SMOKE = "HARNESS_SMOKE_ONLY"
NAMESPACE_FINAL = "FINAL"
SERIES_NAMESPACES = (NAMESPACE_PILOT, NAMESPACE_FINAL)
CONFIGURATIONS = ("C0", "C1", "C2")
FINAL_ORDER_RULE = "EXPERIMENT_PROTOCOL_V0 §11 blocked-by-repetition; per-block derived seed"
DEFAULT_ORDER_SEED_TEXT = "configlab-pilot-v1-order"   # PILOT_PLAN §6
SPEC_SCHEMA = "pilot-series-spec/v0"
SCHEDULE_SCHEMA = "pilot-series-schedule/v0"

# PILOT_PLAN §11: the only classes for which a replacement MAY be approved by the operator.
REPLACEMENT_ELIGIBLE_VALIDITY = ("invalid:infrastructure", "invalid:harness", "preflight_failed")
HALT_VALIDITY = ("invalid:leak", "invalid:carryover")

# A series_halted event's structured category (G10 resume semantics): hard_stop halts (leak,
# carryover, C2 phase-1 write) can never be resumed; recoverable halts (the cleanup-remediation
# path) can be, once explicitly and auditably resumed by the operator. "unknown" is the fail-closed
# default for anything that doesn't structurally match either -- never resumable.
HALT_CATEGORY_HARD_STOP = "hard_stop"
HALT_CATEGORY_RECOVERABLE = "recoverable"
HALT_CATEGORY_UNKNOWN = "unknown"

# Manifest fields that are NOT part of a cell's frozen specification (attempt/runtime identity).
_ATTEMPT_FIELDS = ("run_id", "workspace_token", "created_at", "attempt_ordinal", "attempt_kind",
                   "original_attempt_id", "predecessor_attempt_id", "replacement_reason")


class SeriesError(RuntimeError):
    pass


class SeriesFrozenError(SeriesError):
    """The frozen series specification no longer matches (task/treatment/model/timeout/...)."""


class SeriesNotReady(SeriesError):
    """Real execution requested while required execution values are not concrete."""


class SeriesStateError(SeriesError):
    """The series state forbids the requested action (ambiguous attempt, halt, no approval...)."""


# ------------------------------------------------------------------------------ config/spec --

@dataclass
class SeriesConfig:
    """Operator-authored series inputs (paths are environment details, not part of the spec)."""

    pilot_version: str
    package_dirs: list
    model_request: str = OPEN
    effort_request: str = OPEN
    timeout_seconds: object = OPEN
    claude_md_file: Optional[str] = None
    planning_wrapper_file: Optional[str] = None
    approval_message_file: Optional[str] = None
    order_seed_text: str = DEFAULT_ORDER_SEED_TEXT
    repetitions: int = 1
    max_replacements_per_cell: int = 1
    namespace: str = NAMESPACE_PILOT

    @classmethod
    def from_json(cls, path) -> "SeriesConfig":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        base = path.parent

        def rel(p):
            return None if p is None else str((base / p).resolve()) if not Path(p).is_absolute() else p
        data["package_dirs"] = [rel(p) for p in data["package_dirs"]]
        for k in ("claude_md_file", "planning_wrapper_file", "approval_message_file"):
            data[k] = rel(data.get(k))
        return cls(**data)

    def packages(self) -> list[TaskPackage]:
        return [TaskPackage.load(p) for p in self.package_dirs]

    def treatment(self) -> Treatment:
        def read(p, binary=False):
            if not p or not Path(p).is_file():
                return None
            return Path(p).read_bytes() if binary else Path(p).read_text(encoding="utf-8")
        return Treatment(claude_md=read(self.claude_md_file, binary=True),
                         planning_wrapper=read(self.planning_wrapper_file),
                         approval_message=read(self.approval_message_file))


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def build_spec(config: SeriesConfig) -> dict:
    """The frozen series specification. Everything a replacement must keep identical is here.

    ``PILOT`` and ``FINAL`` share one spec shape (no namespace-specific keys, so the frozen pilot
    serialization is unchanged); ``pilot_version`` is the series identifier for both.
    """
    if config.namespace not in SERIES_NAMESPACES:
        raise SeriesError(f"the series driver runs only the {'/'.join(SERIES_NAMESPACES)} namespaces")
    reps = config.repetitions
    if not isinstance(reps, int) or isinstance(reps, bool) or reps < 1:
        raise SeriesError(f"repetitions must be a positive integer, got {reps!r}")
    t = config.treatment()
    tasks = []
    for pkg in sorted(config.packages(), key=lambda p: p.task_id):
        if config.namespace == NAMESPACE_FINAL and pkg.task_id.startswith("P-"):
            raise SeriesError(f"pilot task {pkg.task_id} can never be part of a FINAL series (F16)")
        gate = pkg.meta.get("validity_gate") or {}
        tasks.append({"task_id": pkg.task_id, "task_version_hash": pkg.version_hash(),
                      "gate_status": gate.get("status"),
                      "gate_task_version_hash": gate.get("task_version_hash"),
                      "statement_hash": pkg.statement_hash, "language": pkg.language,
                      "task_category": pkg.task_category,
                      "evaluator_identity": pkg.evaluator_identity(),
                      "generated_outputs": list(pkg.generated_outputs)})
    spec = {
        "schema": SPEC_SCHEMA, "namespace": config.namespace, "pilot_version": config.pilot_version,
        "configurations": list(CONFIGURATIONS), "repetitions": config.repetitions,
        "order_seed_text": config.order_seed_text,
        "model_request": config.model_request, "effort_request": config.effort_request,
        "timeout_seconds": config.timeout_seconds,
        "treatment": {"claude_md_hash": t.claude_md_hash,
                      "planning_wrapper_hash": t.planning_wrapper_hash,
                      "approval_message_hash": t.approval_message_hash},
        "envelope": {"implementation_envelope_hash": implementation_envelope("C0").envelope_hash(),
                     "planning_envelope_hash": planning_envelope().envelope_hash(),
                     "security_policy_hash": SecurityPolicy().policy_hash()},
        "toolchain": {"claude_code": CLAUDE_CODE_VERSION, "node": NODE_VERSION, "npm": NPM_VERSION,
                      "sandbox_runtime": SANDBOX_RUNTIME_VERSION},
        "replacement_policy": {"max_replacements_per_cell": config.max_replacements_per_cell,
                               "operator_approval_required": True,
                               "eligible_run_validity": list(REPLACEMENT_ELIGIBLE_VALIDITY),
                               "eligible_external_interruption": True,
                               "operator_confirm_run_validity": ["invalid:fixture"],
                               "halt_run_validity": list(HALT_VALIDITY)},
        "tasks": tasks,
    }
    spec["spec_hash"] = canonical_json_hash(spec)
    return spec


def readiness_errors(spec: dict) -> list[str]:
    """Why real execution must be refused (empty = every required execution value is concrete)."""
    errors = []
    if spec["model_request"] in (OPEN, None, ""):
        errors.append("model_request is OPEN")
    if spec["effort_request"] in (OPEN, None, ""):
        errors.append("effort_request is OPEN")
    if not _is_number(spec["timeout_seconds"]) or spec["timeout_seconds"] <= 0:
        errors.append(f"timeout_seconds is not frozen ({spec['timeout_seconds']!r})")
    tr = spec["treatment"]
    if tr["claude_md_hash"] is None:
        errors.append("C1/C2 CLAUDE.md is not frozen")
    if "C2" in spec["configurations"] and (tr["planning_wrapper_hash"] is None
                                           or tr["approval_message_hash"] is None):
        errors.append("C2 planning wrapper / approval message are not frozen")
    if not spec["tasks"]:
        errors.append("no task packages")
    for t in spec["tasks"]:
        if t["gate_status"] != "PASS":
            errors.append(f"{t['task_id']}: validity gate not PASS")
        if t["gate_task_version_hash"] != t["task_version_hash"]:
            errors.append(f"{t['task_id']}: package differs from its gate-passed version")
        if not t["evaluator_identity"]:
            errors.append(f"{t['task_id']}: evaluator identity missing")
    reps = spec.get("repetitions")
    if not isinstance(reps, int) or isinstance(reps, bool) or reps < 1:
        errors.append(f"repetitions must be a positive integer ({reps!r})")
    elif spec["namespace"] == NAMESPACE_PILOT and reps != 1:
        errors.append("a PILOT series has exactly one repetition (PILOT_PLAN §6 defines no other order)")
    return errors


def cell_id_for(spec: dict, task: dict, configuration: str, repetition: int) -> str:
    ident = {"pilot_version": spec["pilot_version"], "task_id": task["task_id"],
             "task_version_hash": task["task_version_hash"], "configuration": configuration,
             "repetition": repetition}
    return "cell-" + canonical_json_hash(ident)[:16]


def generate_schedule(spec: dict) -> dict:
    """The frozen, outcome-independent run order: PILOT_PLAN §6 for ``PILOT``, protocol §11 for
    ``FINAL``. The pilot path is unchanged, so frozen pilot schedules reproduce byte-for-byte."""
    if spec["namespace"] == NAMESPACE_FINAL:
        return _final_schedule(spec)
    return _pilot_schedule(spec)


def final_block_seed(order_seed_text: str, block: int) -> int:
    """Per-block derived seed of the FINAL order (operator decision, Gate 2)."""
    return int(hashlib.sha256(f"{order_seed_text}#block-{block}".encode()).hexdigest()[:8], 16)


def _final_schedule(spec: dict) -> dict:
    """EXPERIMENT_PROTOCOL_V0 §11: blocked by repetition, seeded, non-adaptive.

    Block ``r`` (= repetition ``r``, run in order 1..R) holds every ``task x configuration`` pair
    exactly once, in the order ``random.Random(final_block_seed(seed_text, r)).shuffle`` gives the
    canonical list ``[(task_id, cfg) for task_id in sorted(task_ids) for cfg in C0, C1, C2]``.
    Positions are global (1..pairs*R). The optional "no same task consecutively" constraint (O16)
    is not applied.
    """
    tasks = {t["task_id"]: t for t in spec["tasks"]}
    canonical = [(tid, cfg) for tid in sorted(tasks) for cfg in spec["configurations"]]
    cells, block_seeds, pos = [], [], 0
    for rep in range(1, spec["repetitions"] + 1):
        block_seed = final_block_seed(spec["order_seed_text"], rep)
        block_seeds.append(block_seed)
        perm = list(canonical)
        random.Random(block_seed).shuffle(perm)
        for tid, cfg in perm:
            pos += 1
            cells.append({"position": pos, "cell_id": cell_id_for(spec, tasks[tid], cfg, rep),
                          "task_id": tid, "task_version_hash": tasks[tid]["task_version_hash"],
                          "configuration": cfg, "repetition": rep})
    sched = {"schema": SCHEDULE_SCHEMA, "pilot_version": spec["pilot_version"],
             "spec_hash": spec["spec_hash"], "order_seed_text": spec["order_seed_text"],
             "order_rule": FINAL_ORDER_RULE, "block_seeds": block_seeds, "cells": cells}
    sched["schedule_hash"] = canonical_json_hash(sched)
    return sched


def _pilot_schedule(spec: dict) -> dict:
    """PILOT_PLAN §6, verbatim: seeded, outcome-independent, task-alternating.

    ``seed = int(sha256(seed_text).hexdigest()[:8], 16)``; ``first = rng.choice(tasks)``; tasks
    alternate starting with ``first``; each task gets ``rng.shuffle`` of [C0, C1, C2] (each from
    the canonical list), reshuffled until it differs from the previous task's permutation;
    positions ``t1·c1, t2·c1, t1·c2, t2·c2, t1·c3, t2·c3``.
    """
    if spec["repetitions"] != 1:
        raise SeriesError("PILOT_PLAN §6 defines only the one-repetition pilot order")
    seed = int(hashlib.sha256(spec["order_seed_text"].encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    tasks = {t["task_id"]: t for t in spec["tasks"]}
    ids = sorted(tasks)
    first = rng.choice(ids)
    start = ids.index(first)
    order = ids[start:] + ids[:start]
    perms, prev = {}, None
    for tid in order:
        perm = list(CONFIGURATIONS)
        rng.shuffle(perm)
        while prev is not None and perm == prev:
            perm = list(CONFIGURATIONS)
            rng.shuffle(perm)
        perms[tid], prev = perm, perm
    cells, pos = [], 0
    for k in range(len(CONFIGURATIONS)):
        for tid in order:
            pos += 1
            cfg = perms[tid][k]
            cells.append({"position": pos, "cell_id": cell_id_for(spec, tasks[tid], cfg, 1),
                          "task_id": tid, "task_version_hash": tasks[tid]["task_version_hash"],
                          "configuration": cfg, "repetition": 1})
    sched = {"schema": SCHEDULE_SCHEMA, "pilot_version": spec["pilot_version"],
             "spec_hash": spec["spec_hash"], "order_seed_text": spec["order_seed_text"],
             "seed": seed, "cells": cells}
    sched["schedule_hash"] = canonical_json_hash(sched)
    return sched


def frozen_cell_spec_hash(manifest: RunManifest) -> str:
    d = manifest.to_dict()
    return canonical_json_hash({k: v for k, v in d.items() if k not in _ATTEMPT_FIELDS})


# ------------------------------------------------------------------- decisions/derivation --

def replacement_decision(record: dict) -> str:
    """Deterministic, outcome-quality-independent decision for one attempt record (§10/§11).

    ``complete`` | ``reevaluate`` | ``eligible`` | ``eligible_operator_confirm`` | ``halt`` |
    ``not_eligible``. Uses only run validity / analysis eligibility / C2 protocol -- never
    acceptance or regression verdicts, and never "which configuration looked better".
    """
    status = record["analysis_eligibility"]["status"]
    validity = record["run_validity"]
    if status == AE.COUNTABLE.value:
        return "complete"
    if status == AE.NOT_COUNTABLE_EVALUATION_PENDING.value:
        return "reevaluate"
    if status == AE.NOT_COUNTABLE_EXTERNAL_INTERRUPTION.value:
        return "eligible"
    if validity in HALT_VALIDITY or (validity == "invalid:c2_protocol"
                                     and record.get("c2_protocol") == "phase1_write"):
        return "halt"
    if validity in REPLACEMENT_ELIGIBLE_VALIDITY:
        return "eligible"
    if validity == "invalid:fixture":
        return "eligible_operator_confirm"
    return "not_eligible"


@dataclass
class CellView:
    cell: dict
    state: str = "pending"
    attempts: list = field(default_factory=list)   # [{"started": ev, "end": ev|None, "reeval": [..]}]
    decision: Optional[str] = None


def _effective(att: dict) -> Optional[dict]:
    end = att["end"]
    if end is None:
        return None
    rec = dict(end["record"])
    if att["reevals"]:
        last = att["reevals"][-1]
        rec.update({k: last[k] for k in ("acceptance", "regression", "evaluator_error",
                                         "analysis_eligibility")})
    if att.get("remediations"):
        last = att["remediations"][-1]
        rec.update({k: last[k] for k in ("run_validity", "analysis_eligibility", "invalid_reason")})
    return rec


def _outstanding_halt(events: list[dict]) -> Optional[dict]:
    """The current outstanding ``series_halted`` event, if any (a ``series_resumed`` clears it).

    There is provably at most one outstanding halt at a time: ``_next()`` refuses to start any new
    attempt while halted, so a second halt can never be appended on top of an unresumed one.
    """
    current = None
    for ev in events:
        if ev["event"] == "series_halted":
            current = ev
        elif ev["event"] == "series_resumed":
            current = None
    return current


def _halt_category(halt_event: dict, events: list[dict]) -> str:
    """Structured classification of a halt -- never inferred from the halt event's own free-text
    ``reason`` string, and never resumable on a "recoverable" label alone.

    A halt event's own ``category`` field (set explicitly at the two code sites that raise a halt,
    for every halt this driver version appends) is authoritative for ``hard_stop`` -- that
    classification alone is enough to permanently refuse resume, no further lookup needed. It is
    *not* by itself sufficient for ``recoverable``: a cleanup-failure halt is tagged recoverable at
    the moment cleanup fails, before any remediation has happened, so resumability additionally
    always requires a ``cleanup_remediated`` event for the same attempt whose latest
    ``cleanup_report.residue.all_clear`` is verified ``true`` -- otherwise (no remediation yet, or
    a remediation that did not fully clear the residue) this returns ``unknown`` (fail closed).

    A halt event predating the ``category`` field entirely (a historical event already on disk,
    such as the real pilot-v1 series' own) is first checked structurally against the underlying
    attempt's ``run_validity``/``c2_protocol`` for a hard-stop condition; everything else falls
    through to the same remediation-evidence check as above.
    """
    declared = halt_event.get("category")
    if declared == HALT_CATEGORY_HARD_STOP:
        return HALT_CATEGORY_HARD_STOP
    if declared is None:
        attempt_id = halt_event.get("attempt_id")
        rec = next((ev["record"] for ev in events
                   if ev["event"] == "attempt_finished" and ev["attempt_id"] == attempt_id), None)
        if rec is not None:
            validity = rec.get("run_validity")
            if validity in HALT_VALIDITY or (validity == "invalid:c2_protocol"
                                             and rec.get("c2_protocol") == "phase1_write"):
                return HALT_CATEGORY_HARD_STOP
    attempt_id = halt_event.get("attempt_id")
    remediations = [ev for ev in events if ev["event"] == "cleanup_remediated"
                   and ev["attempt_id"] == attempt_id]
    if remediations and remediations[-1].get("cleanup_report", {}).get("residue", {}).get("all_clear"):
        return HALT_CATEGORY_RECOVERABLE
    return HALT_CATEGORY_UNKNOWN


# -------------------------------------------------------------------------------- driver --

RunnerFactory = Callable[[RunManifest], object]
EvaluatorFactory = Callable[[TaskPackage], object]


@dataclass
class Series:
    root: Path
    config: SeriesConfig
    harness_root: Path
    home: Path = field(default_factory=lambda: Path("/home/cclab"))
    runs_root: Optional[Path] = None
    uid: int = 1001
    git_baseline: bool = True

    def __post_init__(self):
        self.root = Path(self.root)
        self.runs_root = Path(self.runs_root or Path(self.harness_root) / "runs")

    # ------------------------------------------------------------------ files --
    @property
    def attempts_root(self) -> Path:
        return self.root / "attempts"

    def _read(self, name):
        p = self.root / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def _write_once(self, name, obj):
        (self.root / name).write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")

    def events(self) -> list[dict]:
        p = self.root / "events.jsonl"
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def _append(self, event: dict) -> None:
        errs = _validate(event, "pilot-series-event.schema.json")
        if errs:
            raise SeriesError(f"invalid series event: {errs}")
        with open(self.root / "events.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    # ----------------------------------------------------------------- freeze --
    def freeze(self) -> dict:
        """Write spec.json + schedule.json once; re-freezing with different inputs is refused."""
        spec = build_spec(self.config)
        sched = generate_schedule(spec)
        old = self._read("spec.json")
        if old is not None:
            if old["spec_hash"] != spec["spec_hash"] or self._read("schedule.json") != sched:
                raise SeriesFrozenError("series already frozen with a different specification")
            return {"spec_hash": spec["spec_hash"], "schedule_hash": sched["schedule_hash"],
                    "already_frozen": True}
        errs = _validate(spec, "pilot-series-spec.schema.json")
        if errs:
            raise SeriesError(f"invalid series spec: {errs}")
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_once("spec.json", spec)
        self._write_once("schedule.json", sched)
        return {"spec_hash": spec["spec_hash"], "schedule_hash": sched["schedule_hash"],
                "already_frozen": False}

    def frozen(self) -> tuple[dict, dict]:
        spec, sched = self._read("spec.json"), self._read("schedule.json")
        if spec is None or sched is None:
            raise SeriesStateError("series not frozen")
        return spec, sched

    def verify_frozen(self, *, require_ready: bool) -> tuple[dict, dict]:
        """Fail closed if anything the frozen spec pins has changed since freeze (§14)."""
        spec, sched = self.frozen()
        now = build_spec(self.config)
        if now["spec_hash"] != spec["spec_hash"]:
            changed = sorted(k for k in spec if k != "spec_hash" and spec.get(k) != now.get(k))
            raise SeriesFrozenError(f"frozen series specification changed: {changed}")
        if generate_schedule(spec) != sched:
            raise SeriesFrozenError("stored schedule does not match the frozen specification")
        if require_ready:
            errs = readiness_errors(spec)
            if errs:
                raise SeriesNotReady("; ".join(errs))
        return spec, sched

    # ------------------------------------------------------------------ state --
    def cells(self) -> dict[str, CellView]:
        spec, sched = self.frozen()
        views = {c["cell_id"]: CellView(cell=c) for c in sched["cells"]}
        by_attempt, approvals = {}, {}
        for ev in self.events():
            kind = ev["event"]
            if kind == "attempt_started":
                att = {"started": ev, "end": None, "reevals": [], "remediations": []}
                views[ev["cell_id"]].attempts.append(att)
                by_attempt[ev["attempt_id"]] = att
            elif kind in ("attempt_finished", "attempt_aborted"):
                by_attempt[ev["attempt_id"]]["end"] = ev
            elif kind == "reevaluated":
                by_attempt[ev["attempt_id"]]["reevals"].append(ev)
            elif kind == "cleanup_remediated":
                by_attempt[ev["attempt_id"]]["remediations"].append(ev)
            elif kind == "replacement_approved":
                approvals.setdefault(ev["cell_id"], []).append(ev)
        max_repl = spec["replacement_policy"]["max_replacements_per_cell"]
        for cid, v in views.items():
            if not v.attempts:
                continue
            if any(a["end"] is None for a in v.attempts):
                v.state = "ambiguous"
                continue
            if any(_effective(a)["analysis_eligibility"]["status"] == AE.COUNTABLE.value
                   for a in v.attempts):
                v.state, v.decision = "observed", "complete"
                continue
            last = v.attempts[-1]
            v.decision = replacement_decision(_effective(last))
            used = len(v.attempts) - 1
            if v.decision == "reevaluate":
                v.state = "evaluation_pending"
            elif v.decision == "halt":
                v.state = "halted"
            elif v.decision in ("eligible", "eligible_operator_confirm"):
                approved = [a for a in approvals.get(cid, [])
                            if a["after_attempt_id"] == last["started"]["attempt_id"]]
                if used >= max_repl:
                    v.state = "no_valid_attempt"
                elif approved:
                    v.state = "replacement_approved"
                else:
                    v.state = "replacement_eligible"
            else:
                v.state = "no_valid_attempt"
        return views

    def halted(self) -> bool:
        """Effective halt state: an outstanding (not yet validly resumed) series_halted event.

        Not "a halt ever happened" -- a recoverable halt that was explicitly, auditably resumed
        (:meth:`resume`) is no longer outstanding, while a hard-stop halt can never be resumed and
        so remains outstanding (and thus ``True``) forever.
        """
        return _outstanding_halt(self.events()) is not None

    def status(self) -> dict:
        spec, sched = self.frozen()
        views = self.cells()
        return {"pilot_version": spec["pilot_version"], "spec_hash": spec["spec_hash"],
                "schedule_hash": sched["schedule_hash"], "halted": self.halted(),
                "readiness_errors": readiness_errors(spec),
                "cells": [{"position": v.cell["position"], "cell_id": cid,
                           "task_id": v.cell["task_id"], "configuration": v.cell["configuration"],
                           "repetition": v.cell["repetition"], "state": v.state, "decision": v.decision,
                           "attempts": [a["started"]["attempt_id"] for a in v.attempts]}
                          for cid, v in views.items()]}

    def _next(self):
        _, sched = self.frozen()
        views = self.cells()
        if self.halted():
            raise SeriesStateError("series halted for operator review")
        amb = [cid for cid, v in views.items() if v.state == "ambiguous"]
        if amb:
            raise SeriesStateError(f"ambiguous attempt(s) in {amb}: run recover() first")
        for c in sched["cells"]:                       # originals first, in schedule order
            if views[c["cell_id"]].state == "pending":
                return c, views[c["cell_id"]], "original"
        for c in sched["cells"]:                       # then approved replacements, same order
            if views[c["cell_id"]].state == "replacement_approved":
                return c, views[c["cell_id"]], "replacement"
        return None, None, None

    def plan_next(self) -> dict:
        """Dry run: safe metadata only. Creates no manifest, workspace or results directory."""
        spec, sched = self.frozen()
        cell, view, kind = self._next()
        out = {"model_request_frozen": spec["model_request"] != OPEN,
               "effort_frozen": spec["effort_request"] != OPEN,
               "timeout_frozen": _is_number(spec["timeout_seconds"]),
               "readiness_errors": readiness_errors(spec)}
        if cell is None:
            return {**out, "next": None}
        return {**out, "next": {"position": cell["position"], "cell_id": cell["cell_id"],
                                "task_id": cell["task_id"], "configuration": cell["configuration"],
                                "repetition": cell["repetition"], "attempt_kind": kind,
                                "attempt_ordinal": len(view.attempts) + 1}}

    # -------------------------------------------------------------- manifests --
    def build_manifest(self, spec, sched, cell, *, kind, ordinal, original=None, predecessor=None,
                       reason=None) -> RunManifest:
        task = next(t for t in spec["tasks"] if t["task_id"] == cell["task_id"])
        cfg = cell["configuration"]
        tr = spec["treatment"]
        m = RunManifest(
            run_id=new_run_id(), task_id=task["task_id"], task_version_hash=task["task_version_hash"],
            language=task["language"], task_category=task["task_category"], configuration=cfg,
            repetition=cell["repetition"], workspace_token=new_workspace_token(),
            settings_policy_hash=implementation_envelope(cfg).envelope_hash(),
            security_policy_hash=SecurityPolicy().policy_hash(),
            task_statement_hash=task["statement_hash"],
            implementation_tool_set=IMPLEMENTATION_TOOLS,
            planning_tool_set=PLANNING_TOOLS if cfg == "C2" else None,
            claude_md_hash=tr["claude_md_hash"] if cfg in ("C1", "C2") else None,
            planning_wrapper_hash=tr["planning_wrapper_hash"] if cfg == "C2" else None,
            approval_message_hash=tr["approval_message_hash"] if cfg == "C2" else None,
            order_position=cell["position"], order_seed_ref=sched["schedule_hash"],
            model_request=spec["model_request"], effort_request=spec["effort_request"],
            timeout_seconds=spec["timeout_seconds"],
            namespace=spec["namespace"], series_id=spec["pilot_version"],
            series_spec_hash=spec["spec_hash"], cell_id=cell["cell_id"],
            attempt_ordinal=ordinal, attempt_kind=kind, original_attempt_id=original,
            predecessor_attempt_id=predecessor, replacement_reason=reason,
        )
        errs = m.validate()
        if errs:
            raise SeriesError(f"attempt manifest invalid: {errs}")
        return m

    # ---------------------------------------------------------------- execute --
    def execute_next(self, runner_factory: RunnerFactory, evaluator_factory: EvaluatorFactory,
                     *, cleanup_runner=None, preflight_checks=None) -> dict:
        """Run exactly ONE attempt (the next original, else the next approved replacement)."""
        from .lifecycle import RunLifecycle
        from .session import SessionSpec, new_session_uuid

        spec, sched = self.verify_frozen(require_ready=True)
        cell, view, kind = self._next()
        if cell is None:
            return {"executed": None, "done": True}
        ordinal = len(view.attempts) + 1
        original = predecessor = reason = None
        if kind == "replacement":
            first, last = view.attempts[0]["started"], view.attempts[-1]["started"]
            original, predecessor = first["attempt_id"], last["attempt_id"]
            reason = next(e for e in reversed(self.events()) if e["event"] == "replacement_approved"
                          and e["cell_id"] == cell["cell_id"])["reason"]
        manifest = self.build_manifest(spec, sched, cell, kind=kind, ordinal=ordinal,
                                       original=original, predecessor=predecessor, reason=reason)
        frozen = frozen_cell_spec_hash(manifest)
        if kind == "replacement" and frozen != view.attempts[0]["started"]["frozen_cell_spec_hash"]:
            raise SeriesFrozenError("replacement would not use the original cell's frozen specification")
        pkg = next(p for p in self.config.packages() if p.task_id == cell["task_id"])
        treatment = self.config.treatment()
        cfg = cell["configuration"]
        treat = None if cfg == "C0" else (Treatment(claude_md=treatment.claude_md) if cfg == "C1"
                                          else treatment)
        # Everything that can be refused is refused BEFORE the attempt is recorded as started.
        runner = runner_factory(manifest)
        if getattr(runner, "model", manifest.model_request) != manifest.model_request:
            raise SeriesFrozenError("agent runner model differs from the frozen model_request")
        if getattr(runner, "effort", manifest.effort_request) != manifest.effort_request:
            raise SeriesFrozenError("agent runner effort differs from the frozen effort_request")
        evaluator = evaluator_factory(pkg)
        self._append({"event": "attempt_started", "attempt_id": manifest.run_id,
                      "cell_id": cell["cell_id"], "position": cell["position"], "ordinal": ordinal,
                      "kind": kind, "original_attempt_id": original,
                      "predecessor_attempt_id": predecessor, "replacement_reason": reason,
                      "manifest_hash": canonical_json_hash(manifest.to_dict()),
                      "frozen_cell_spec_hash": frozen})
        life = RunLifecycle(pristine=pkg.pristine, runs_root=self.runs_root,
                            results_root=self.attempts_root, home=Path(self.home), uid=self.uid,
                            harness_root=Path(self.harness_root), git_baseline=self.git_baseline,
                            generated_outputs=pkg.generated_outputs)
        try:
            life.execute(manifest=manifest, envelope=implementation_envelope(cfg),
                         session=SessionSpec("new", new_session_uuid()),
                         evaluator=evaluator, agent_runner=runner,
                         cleanup_runner=cleanup_runner, preflight_checks=preflight_checks,
                         treatment=treat, task_statement=pkg.statement())
        except Exception as exc:   # the attempt happened but did not finalize: recorded, not retried
            self._append({"event": "attempt_aborted", "attempt_id": manifest.run_id,
                          "error_type": type(exc).__name__, "record": _ABORTED_RECORD})
            raise
        record = self._finished_record(manifest.run_id)
        self._append({"event": "attempt_finished", "attempt_id": manifest.run_id, "record": record})
        decision = replacement_decision(record)
        # A real (non-Dry) cleanup that failed or left residue is tagged invalid:harness with an
        # "cleanup_failed: ..." invalid_reason by lifecycle._finalize(); that alone already makes
        # the cell replacement-eligible via `decision`, but the series must also stop outright
        # (protocol: no unexplained state carryover between runs) rather than silently letting a
        # later cell in schedule order run next -- reuse the existing halt mechanism for that.
        cleanup_halt = str(record.get("invalid_reason") or "").startswith("cleanup_failed:")
        if decision == "halt" or cleanup_halt:
            self._append({"event": "series_halted", "attempt_id": manifest.run_id,
                          "reason": record["run_validity"] if decision == "halt" else "cleanup_failed",
                          "category": HALT_CATEGORY_HARD_STOP if decision == "halt"
                                     else HALT_CATEGORY_RECOVERABLE})
        return {"executed": manifest.run_id, "cell_id": cell["cell_id"], "kind": kind,
                "ordinal": ordinal, "decision": decision, "record": record}

    def _finished_record(self, attempt_id: str) -> dict:
        run_dir = self.attempts_root / attempt_id
        res = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        c2 = run_dir / "c2.json"
        phases = len(json.loads(c2.read_text(encoding="utf-8")).get("phases", [])) if c2.exists() else None
        return {k: res.get(k) for k in ("agent_outcome", "run_validity", "acceptance", "regression",
                                        "evaluator_error", "c2_protocol", "analysis_eligibility",
                                        "invalid_reason")} \
            | {"c2_phase2_reached": None if phases is None else phases >= 2,
               "cleanup_performed": res.get("cleanup", {}).get("performed")}

    # ------------------------------------------------------------ operator ops --
    def approve_replacement(self, cell_id: str, reason: str, note: str = "") -> dict:
        """Record the operator's replacement decision (PILOT_PLAN §11: never automatic)."""
        self.verify_frozen(require_ready=False)
        view = self.cells().get(cell_id)
        if view is None:
            raise SeriesStateError(f"unknown cell {cell_id}")
        if view.state != "replacement_eligible":
            raise SeriesStateError(f"cell {cell_id} is {view.state}; no replacement may be approved")
        if view.decision == "eligible_operator_confirm" and not note:
            raise SeriesStateError("invalid:fixture replacement needs an operator note confirming "
                                   "the materialized copy (not the package) was corrupted")
        ev = {"event": "replacement_approved", "cell_id": cell_id, "reason": reason, "note": note,
              "after_attempt_id": view.attempts[-1]["started"]["attempt_id"]}
        self._append(ev)
        return ev

    def recover(self, attempt_id: str) -> dict:
        """Resolve an ambiguous attempt (driver crashed after start) without re-executing it."""
        from .result import audit_run_directory

        views = self.cells()
        att = next((a for v in views.values() for a in v.attempts
                    if a["started"]["attempt_id"] == attempt_id), None)
        if att is None or att["end"] is not None:
            raise SeriesStateError(f"attempt {attempt_id} is not ambiguous")
        run_dir = self.attempts_root / attempt_id
        if (run_dir / "result.json").exists() and not audit_run_directory(run_dir):
            ev = {"event": "attempt_finished", "attempt_id": attempt_id,
                  "record": self._finished_record(attempt_id), "recovered": True}
        else:
            ev = {"event": "attempt_aborted", "attempt_id": attempt_id,
                  "error_type": "driver_interrupted", "record": _ABORTED_RECORD}
        self._append(ev)
        return ev

    def reevaluate(self, attempt_id: str, evaluator) -> dict:
        """Re-run the evaluator on the attempt's preserved final state (evaluation_pending only).

        The agent evidence and result.json are never rewritten; the re-evaluation is appended to
        ``reevaluation.json`` and to the series event log.
        """
        from .agent_state import take_snapshot
        from .artifacts import ArtifactStore
        from .status import derive_analysis_eligibility

        self.verify_frozen(require_ready=False)
        view = next((v for v in self.cells().values()
                     if any(a["started"]["attempt_id"] == attempt_id for a in v.attempts)), None)
        if view is None or view.state != "evaluation_pending" \
                or view.attempts[-1]["started"]["attempt_id"] != attempt_id:
            raise SeriesStateError(f"attempt {attempt_id} is not evaluation_pending")
        run_dir = self.attempts_root / attempt_id
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        final = json.loads((run_dir / "final_state.json").read_text(encoding="utf-8"))
        wc = self.runs_root / manifest["workspace_token"]
        pkg = next(p for p in self.config.packages() if p.task_id == manifest["task_id"])
        if not wc.is_dir() or take_snapshot(wc, pkg.generated_outputs).tree_hash != final["tree_hash"]:
            raise SeriesStateError("preserved final working copy is missing or changed; "
                                   "re-evaluation refused")
        ev = evaluator.evaluate(wc)
        res = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        status, reason = derive_analysis_eligibility(
            res["run_validity"], res["agent_outcome"], acceptance=ev.acceptance,
            regression=ev.regression, evaluator_error=ev.evaluator_error)
        entry = {"acceptance": ev.acceptance.value, "regression": ev.regression.value,
                 "evaluator_error": ev.evaluator_error, "integrity": ev.integrity.value,
                 "analysis_eligibility": {"status": status.value, "reason": reason},
                 "evaluation": ev.to_dict()}
        history_path = run_dir / "reevaluation.json"
        history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
        store = ArtifactStore(run_dir=run_dir)
        store.write_safe("reevaluation.json", history + [entry])
        event = {"event": "reevaluated", "attempt_id": attempt_id,
                 **{k: entry[k] for k in ("acceptance", "regression", "evaluator_error",
                                          "analysis_eligibility")}}
        self._append(event)
        return event

    def remediate_cleanup(self, attempt_id: str, *, cleanup_report: dict, reason: str) -> dict:
        """Retroactively correct an attempt whose ORIGINAL cleanup never actually ran/succeeded
        (a production wiring defect, not a normal outcome) to infrastructure-invalid/non-countable.

        The original ``result.json``/manifest/evidence are never rewritten (PILOT_PLAN: no
        unexplained state carryover between runs, but also no rewriting history) -- the correction
        lives entirely in one new append-only event, overlaid onto the effective record the same
        way :meth:`reevaluate`'s corrections are. ``cleanup_report`` is the finished post-hoc
        cleanup's own command/status/residue evidence; the caller runs that cleanup for real and
        hands in the result (this method itself makes no subprocess/filesystem calls, mirroring how
        :meth:`reevaluate` takes an already-built evaluator) -- kept on this event only, distinct
        from the original attempt's own ``cleanup.json``, which is never touched.

        Halts the series (if not already halted), since the only existing mechanism that stops a
        later cell from running while this one is unresolved is the series-wide halt flag.
        """
        from .status import RunValidity, derive_analysis_eligibility

        self.verify_frozen(require_ready=False)
        view = next((v for v in self.cells().values()
                     if v.attempts and v.attempts[-1]["started"]["attempt_id"] == attempt_id), None)
        if view is None:
            raise SeriesStateError(f"unknown or non-final attempt {attempt_id}")
        # "observed" is the historical mis-classification shape (this defect, pre-fix); a real
        # cleanup failure since the fix is already correctly classified invalid:harness /
        # replacement_eligible at finalize time -- remediate_cleanup is still how the operator
        # records the real post-hoc cleanup's evidence for that case (needed for resume()), it
        # just has nothing to *correct* in the classification. Either shape is eligible exactly
        # once (guarded below by event existence, not cell state, so a corrected cell doesn't look
        # "already remediated" for the wrong reason).
        if view.state not in ("observed", "replacement_eligible"):
            raise SeriesStateError(f"attempt {attempt_id}'s cell is {view.state}; nothing to remediate")
        if any(ev["event"] == "cleanup_remediated" and ev["attempt_id"] == attempt_id
              for ev in self.events()):
            raise SeriesStateError(f"attempt {attempt_id} already has a cleanup remediation recorded")
        run_dir = self.attempts_root / attempt_id
        res = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        if res.get("cleanup", {}).get("performed") is not False:
            raise SeriesStateError(f"attempt {attempt_id}'s original cleanup already performed; "
                                   "remediate_cleanup is only for the historical no-op-cleanup defect")
        new_validity = RunValidity.INVALID_HARNESS
        status, ae_reason = derive_analysis_eligibility(
            new_validity.value, res["agent_outcome"], acceptance=res["acceptance"],
            regression=res["regression"], evaluator_error=res["evaluator_error"])
        event = {"event": "cleanup_remediated", "attempt_id": attempt_id,
                 "run_validity": new_validity.value,
                 "invalid_reason": f"cleanup_failed: {reason}",
                 "analysis_eligibility": {"status": status.value, "reason": ae_reason},
                 "cleanup_report": cleanup_report}
        self._append(event)
        if not self.halted():
            self._append({"event": "series_halted", "attempt_id": attempt_id,
                          "reason": "cleanup_remediated: historical residue found; "
                                    "operator review required",
                          "category": HALT_CATEGORY_RECOVERABLE})
        return event

    def resume(self, *, reason: str, note: str = "") -> dict:
        """Explicitly, auditably resume the series from its current outstanding halt -- but only
        when that halt is structurally classified :data:`HALT_CATEGORY_RECOVERABLE`
        (:func:`_halt_category`). Fail closed for every other case: no outstanding halt, a
        hard-stop halt (leak/carryover/C2 phase-1 write -- these must never become resumable), an
        unknown/unrecognized halt, a ``cleanup_remediated`` whose residue was not fully clear
        (folded into "unknown" by :func:`_halt_category`), or a cell that is not itself in a
        replacement-eligible/-approved state.

        Appends exactly one new ``series_resumed`` event; never edits or removes the prior
        ``series_halted`` event (append-only history), never approves a replacement, never
        executes an attempt. ``reason`` is the operator's mandatory justification; ``note`` is an
        optional explanation of why this specific halt qualifies as recoverable (defaults to a
        generic description when omitted).
        """
        self.verify_frozen(require_ready=False)
        events = self.events()
        outstanding = _outstanding_halt(events)
        if outstanding is None:
            raise SeriesStateError("series is not currently halted; nothing to resume")
        category = _halt_category(outstanding, events)
        if category != HALT_CATEGORY_RECOVERABLE:
            raise SeriesStateError(f"halt is not recoverable (category={category!r}); resume refused")
        attempt_id = outstanding.get("attempt_id")
        views = self.cells()
        cid = next((cid for cid, v in views.items()
                   if any(a["started"]["attempt_id"] == attempt_id for a in v.attempts)), None)
        if cid is None or views[cid].state not in ("replacement_eligible", "replacement_approved"):
            state = views[cid].state if cid is not None else "unknown cell"
            raise SeriesStateError(f"cell for attempt {attempt_id} is {state}; not eligible to resume")
        ev = {"event": "series_resumed", "attempt_id": attempt_id, "cell_id": cid,
              "resolves_reason": outstanding.get("reason"), "resolves_category": category,
              "operator_reason": reason,
              "recoverable_basis": note or "cleanup remediated; residue verified clear; "
                                          "cell replacement-eligible under the frozen policy"}
        self._append(ev)
        return ev


_ABORTED_RECORD = {"agent_outcome": "harness_error", "run_validity": "invalid:harness",
                   "acceptance": "not_run", "regression": "not_run", "evaluator_error": False,
                   "c2_protocol": None, "c2_phase2_reached": None,
                   "analysis_eligibility": {"status": AE.NOT_COUNTABLE_INVALID.value,
                                            "reason": "invalid:harness/attempt_not_finalized"}}


def _validate(obj: dict, schema_name: str) -> list[str]:
    from . import schema as _schema
    from ._schemas import load_schema

    return _schema.validate(obj, load_schema(schema_name))


# ------------------------------------------------------------------------- guards --

def load_pilot_attempt(run_dir) -> dict:
    """Load an attempt's manifest as a PILOT attempt; refuses smoke/unlinked/final records."""
    manifest = json.loads((Path(run_dir) / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("namespace") != NAMESPACE_PILOT or not manifest.get("cell_id"):
        raise SeriesError("not a pilot-series attempt (namespace/cell identity missing)")
    return manifest


def assert_promotable_to_final(manifest: dict) -> None:
    """Pilot (and smoke) attempts can never become final results (FROZEN F16)."""
    if manifest.get("namespace") != NAMESPACE_FINAL or str(manifest.get("task_id", "")).startswith("P-"):
        raise SeriesError("only FINAL-namespace attempts of final tasks are final results")
