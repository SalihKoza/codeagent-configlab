"""Per-run lifecycle skeleton (protocol §15).

Wires the primitives into the fixed sequence:

    PREPARE -> AGENT RUN -> CAPTURE FINAL STATE -> EVALUATE -> CAPTURE RESULTS
            -> PURGE CLAUDE PROJECT STATE -> EXACT-NAME CLEANUP -> DONE

Cleanup never runs before artifacts are captured. The agent-run and cleanup steps are
**pluggable**: offline tests use dry runners (no ``claude``/``srt``/network); a real end-to-end
smoke run supplies runners that shell out — that entry point is labelled ``HARNESS_SMOKE_ONLY``
and is not exercised in this task.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol

from .artifacts import (WRITE_FAILED, ArtifactFinalizationError, ArtifactSecretError, ArtifactStore,
                        withhold_markers)
from .cleanup import build_cleanup_plan, plan_to_dict, verify_residue
from .envelope import ExecutionEnvelope
from .evaluator import EvaluationResult, Evaluator
from .manifest import RunManifest
from .sentinels import OPEN
from .preflight import PreflightContext, run_preflight
from .result import ArtifactRefs, CleanupRef, RunResult
from .session import SessionSpec
from .status import AgentOutcome, RunValidity, Acceptance, Regression, Integrity, C2Protocol
from .workspace import WorkingCopy, changed_files, make_working_copy


@dataclass
class AgentRunOutcome:
    """What an agent-run step reports back to the lifecycle."""

    exit_code: Optional[int]  # None when the harness terminated the process (cap) or never ran it
    session_id: Optional[str]
    agent_outcome: AgentOutcome = AgentOutcome.COMPLETED
    stdout: str = ""
    stderr: str = ""
    events: list[dict] = field(default_factory=list)
    phase1_exit_code: Optional[int] = None
    phase2_exit_code: Optional[int] = None
    session_continuity_verified: bool = False
    detail: str = ""                      # short classification reason (timeout / harness error)
    process: Optional[dict] = None        # termination metadata (ProcessRunResult.metadata())
    observed_model: Optional[str] = None  # structured init-event "model" field, if any (never text)


class AgentRunner(Protocol):
    def run(
        self, working_copy: WorkingCopy, envelope: ExecutionEnvelope, session: SessionSpec,
        *, prompt: Optional[str] = None, deadline=...,
    ) -> AgentRunOutcome:
        """One CLI invocation. ``prompt``/``deadline`` are per-call (see RealAgentRunner.run)."""
        ...


class CleanupRunner(Protocol):
    def execute(self, plan) -> dict: ...


@dataclass
class DryAgentRunner:
    """Offline agent stand-in: never invokes claude.

    Optionally applies ``mutate`` to the working copy to simulate an agent edit (used by smoke
    tests to make the evaluator meaningful), and synthesizes ``init``/``result`` stream-json
    events reporting the expected session id so continuity plumbing can be exercised. ``model``,
    if given, is echoed into the synthetic init event and ``observed_model`` (a dry run against a
    frozen ``model_request`` must not spuriously read as a model-provenance violation).
    """

    mutate: Optional[Callable[[Path], None]] = None
    model: Optional[str] = None

    def run(self, working_copy, envelope, session, *, prompt=None, deadline=None) -> AgentRunOutcome:
        if self.mutate is not None:
            self.mutate(working_copy.path)
        sid = session.session_id
        init_event = {"type": "system", "subtype": "init", "session_id": sid}
        if self.model is not None:
            init_event["model"] = self.model
        events = [
            init_event,
            {"type": "result", "subtype": "success", "is_error": False, "session_id": sid},
        ]
        return AgentRunOutcome(
            exit_code=0,
            session_id=sid,
            agent_outcome=AgentOutcome.COMPLETED,
            stdout="[dry-run] no agent invoked",
            stderr="",
            events=events,
            session_continuity_verified=True,
            observed_model=self.model,
        )


@dataclass
class DryCleanupRunner:
    """Records the cleanup plan without executing any command (offline)."""

    def execute(self, plan) -> dict:
        report = plan_to_dict(plan)
        report["executed"] = False
        return report


@dataclass
class RunLifecycle:
    """Executes one run end-to-end using injected runners."""

    pristine: Path
    runs_root: Path
    results_root: Path
    home: Path = field(default_factory=lambda: Path("/home/cclab"))
    uid: int = 1001
    harness_root: Optional[Path] = None
    git_baseline: bool = True   # protocol §4 / G6: every WC starts from the neutral pristine commit
    # task-package-declared build/runtime outputs (TaskPackage.generated_outputs); identical for
    # C0/C1/C2 because it comes from the package, never from the configuration
    generated_outputs: tuple = ()

    def execute(
        self,
        manifest: RunManifest,
        envelope: ExecutionEnvelope,
        session: SessionSpec,
        evaluator: Evaluator,
        agent_runner: AgentRunner,
        cleanup_runner: Optional[CleanupRunner] = None,
        preflight_checks: Optional[list] = None,
        treatment=None,
        task_statement: Optional[str] = None,
        budget_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> RunResult:
        """Run one experimental unit.

        ``session.session_id`` is the run's session UUID; for C2 the orchestrator uses it with
        ``--session-id`` in phase 1 and ``--resume`` in phase 2. ``treatment`` carries the frozen
        C1/C2 material; the expected working-copy state is taken from the manifest hashes.
        ``budget_seconds`` (else a numeric ``manifest.timeout_seconds``) is the single wall-clock
        budget of the run; without one, C0/C1 fall back to the runner's own timeout and C2 runs
        uncapped (never a separate full cap per phase).
        """
        from .orchestration import run_agent_condition
        from .treatment import (expected_treatment_files, materialize_treatment,
                                treatment_provenance_errors)

        # G10: the manifest is the executable truth. A frozen (numeric) timeout cannot be
        # overridden by a separately supplied budget, and a runner cannot use another model.
        # Refused before anything is created or started.
        frozen_timeout = isinstance(manifest.timeout_seconds, (int, float)) \
            and not isinstance(manifest.timeout_seconds, bool)
        if frozen_timeout and budget_seconds is not None \
                and float(budget_seconds) != float(manifest.timeout_seconds):
            raise ValueError("budget_seconds differs from the frozen manifest timeout_seconds")
        runner_model = getattr(agent_runner, "model", None)
        if runner_model is not None and manifest.model_request != OPEN \
                and runner_model != manifest.model_request:
            raise ValueError("agent runner model differs from the frozen manifest model_request")
        runner_effort = getattr(agent_runner, "effort", None)
        if runner_effort is not None and manifest.effort_request != OPEN \
                and runner_effort != manifest.effort_request:
            raise ValueError("agent runner effort differs from the frozen manifest effort_request")

        from .agent_state import validate_generated_patterns

        bad = validate_generated_patterns(self.generated_outputs)
        if bad:
            raise ValueError(f"invalid generated_outputs: {bad}")

        cleanup_runner = cleanup_runner or DryCleanupRunner()
        result = RunResult(run_id=manifest.run_id)
        store = ArtifactStore.create(self.results_root, manifest.run_id)
        result.started_at = _utc_now()
        t0 = time.monotonic()
        config = manifest.configuration
        expected = expected_treatment_files(manifest)

        # 1. PREPARE ---------------------------------------------------------------
        seeded = envelope.security_policy.seed_wc_settings
        wc = make_working_copy(self.pristine, self.runs_root, seed_settings=seeded,
                               token=manifest.workspace_token, git_baseline=self.git_baseline)
        # Treatment is added after the neutral commit and stays uncommitted (same history for
        # C0/C1/C2).
        materialize_treatment(wc.path, config, treatment)
        ctx = PreflightContext(
            working_copy=wc.path, home=self.home, pristine=self.pristine,
            harness_root=self.harness_root, session_uuid=session.session_id, uid=self.uid,
            expected_treatment_files=expected,
            provenance_errors=treatment_provenance_errors(manifest, treatment, task_statement),
        )
        pre = run_preflight(ctx, preflight_checks)
        if self.git_baseline:
            from .baseline import baseline_record, cached_expected_baseline_commit
            from .preflight import CheckOutcome
            from .status import Preflight

            brec = baseline_record(self.pristine, cached_expected_baseline_commit(self.pristine),
                                   wc.baseline_commit)
            store.write_safe("baseline.json", brec)
            pre.outcomes.append(CheckOutcome(
                "baseline_commit", Preflight.OK if brec["matches"] else Preflight.FAILED,
                f"expected {brec['expected_commit']}, observed {brec['observed_commit']}"))
        store.write_safe("preflight.json", pre.to_dict())
        if not pre.ok:
            result.run_validity = RunValidity.PREFLIGHT_FAILED
            result.agent_outcome = AgentOutcome.HARNESS_ERROR
            result.invalid_reason = "preflight failed: " + "; ".join(
                o.detail for o in pre.outcomes if o.status.value == "failed"
            )
            return self._finalize(result, store, manifest, t0, wc, session, cleanup_runner)

        # Agent-visible start state = pristine + runtime seeds + treatment (not the neutral
        # baseline). Everything the agent did is measured against this.
        from .agent_state import take_snapshot
        from .treatment import expected_start_instruction_state, instruction_state

        start_state = take_snapshot(wc.path, self.generated_outputs)
        store.write_safe("start_state.json", start_state.to_dict())
        expected_start = expected_start_instruction_state(expected, seeded)

        if budget_seconds is None and isinstance(manifest.timeout_seconds, (int, float)) \
                and not isinstance(manifest.timeout_seconds, bool):
            budget_seconds = float(manifest.timeout_seconds)

        # 2. AGENT RUN (one invocation for C0/C1, two phases for C2) -----------------
        try:
            cond = run_agent_condition(
                configuration=config, runner=agent_runner, working_copy=wc, envelope=envelope,
                session_uuid=session.session_id, home=self.home, task_statement=task_statement,
                treatment=treatment, budget_seconds=budget_seconds, clock=clock,
            )
        except Exception as exc:  # a harness/runner fault, not a task outcome
            result.run_validity = RunValidity.INVALID_HARNESS
            result.agent_outcome = AgentOutcome.HARNESS_ERROR
            result.harness_failure = True
            result.invalid_reason = f"agent runner raised: {exc}"
            return self._finalize(result, store, manifest, t0, wc, session, cleanup_runner)
        outcome = cond.outcome

        result.agent_exit_code = outcome.exit_code
        result.phase1_exit_code = outcome.phase1_exit_code
        result.phase2_exit_code = outcome.phase2_exit_code
        result.observed_session_id = outcome.session_id
        result.session_continuity_verified = outcome.session_continuity_verified
        result.agent_outcome = outcome.agent_outcome
        result.c2_protocol = cond.c2_protocol

        # Classify infrastructure outcomes (protocol §10). Auth failure and subscription-limit
        # are NOT task outcomes; a harness_error means the runner itself failed. These keep
        # precedence over a C2 protocol violation.
        infra_stop = False
        if outcome.agent_outcome is AgentOutcome.AUTH_FAILURE:
            result.run_validity = RunValidity.INVALID_INFRASTRUCTURE
            result.auth_failure = True
            # G4: the classifier's reason code names the structured evidence (see process.json)
            result.invalid_reason = ("infrastructure auth failure"
                                     + (f" ({outcome.detail})" if outcome.detail else " (see events)"))
            infra_stop = True
        elif outcome.agent_outcome is AgentOutcome.LIMIT_INTERRUPTED:
            # G3: an external execution interruption -- run_validity stays VALID (nothing about the
            # experiment was wrong) and result.json derives not_countable:external_interruption.
            result.limit_interrupted = True
            result.interruption_reason = ("subscription limit interruption"
                                          + (f" ({outcome.detail})" if outcome.detail else ""))
            infra_stop = True
        elif outcome.agent_outcome is AgentOutcome.HARNESS_ERROR:
            result.run_validity = RunValidity.INVALID_HARNESS
            result.harness_failure = True
            result.invalid_reason = outcome.detail or "agent runner reported a harness error"
            infra_stop = True
        elif outcome.agent_outcome is AgentOutcome.TIMEOUT:
            # A correctly enforced cap is an experimental outcome (protocol §10): the run stays
            # valid and the final state is still evaluated. Never retried here.
            result.interruption_reason = outcome.detail or "wall-clock cap reached"
        if not infra_stop and cond.c2_protocol in (C2Protocol.PHASE1_WRITE,
                                                   C2Protocol.PHASE_TRANSITION_FAILED):
            # The C2 treatment was not delivered as specified (protocol §8): invalid, not a task
            # outcome, and not scored.
            result.run_validity = RunValidity.INVALID_C2_PROTOCOL
            result.invalid_reason = f"c2 protocol violation ({cond.c2_protocol.value}): {cond.c2_detail}"
            infra_stop = True

        # Model provenance: requested (manifest.model_request) vs. observed (the CLI's structured
        # init-event "model" field, session.observed_model_in_events) -- never assistant/tool text.
        # Only evaluated once the model is actually frozen, and only for COMPLETED/TIMEOUT/ERROR_EXIT
        # (an already-explained AUTH_FAILURE/LIMIT_INTERRUPTED/HARNESS_ERROR is never overridden
        # here -- those already set infra_stop above, so auth/limit before init are unaffected). A
        # mismatch is an execution/provenance violation, not a task/acceptance failure: it maps to
        # the existing invalid:harness status (PILOT_PLAN §7), which is already non-countable
        # (status.derive_analysis_eligibility) and already replacement-eligible
        # (series.REPLACEMENT_ELIGIBLE_VALIDITY) with no new policy needed.
        #
        # ERROR_EXIT is asymmetric: a genuine trusted init event DID happen, so a mismatch must
        # still fail closed (it must not become invisible just because the run later errored
        # ordinarily) -- but when ERROR_EXIT happened before any init event, there is no
        # model-provenance evidence at all, and that absence is never invented into a verdict: the
        # run keeps today's ordinary error_exit semantics (run_validity left untouched here).
        if not infra_stop and manifest.model_request != OPEN \
                and outcome.agent_outcome in (AgentOutcome.COMPLETED, AgentOutcome.TIMEOUT,
                                              AgentOutcome.ERROR_EXIT):
            mismatched = [(p.label, p.observed_model) for p in cond.phases
                         if p.observed_model is not None and p.observed_model != manifest.model_request]
            missing = [p.label for p in cond.phases if p.observed_model is None]
            if mismatched:
                result.run_validity = RunValidity.INVALID_HARNESS
                detail = ", ".join(f"{label}={om!r}" for label, om in mismatched)
                result.invalid_reason = (f"observed model mismatch "
                                         f"(requested={manifest.model_request!r}): {detail}")
                infra_stop = True
            elif missing and outcome.agent_outcome is not AgentOutcome.ERROR_EXIT:
                # COMPLETED/TIMEOUT with no observed model is anomalous and fails closed; an
                # ERROR_EXIT with no observed model has no evidence to verify -- not invented.
                result.run_validity = RunValidity.INVALID_HARNESS
                result.invalid_reason = f"no observed model captured for: {', '.join(missing)}"
                infra_stop = True

        # 3. CAPTURE FINAL STATE (before any evaluator copy exists) ---------------------
        from .agent_state import capture_final_state

        final_state, invariant = capture_final_state(
            store=store, result=result, working_copy=wc.path, pristine=self.pristine,
            start_state=start_state, expected_start=expected_start, treatment=treatment,
            seeded=seeded, configuration=config, baseline_commit=wc.baseline_commit,
            generated=self.generated_outputs,
        )
        if not invariant["ok"] and not infra_stop and result.run_validity is RunValidity.VALID:
            # The instruction state the treatment defines changed during the run: not a comparable
            # task outcome. Nothing is restored; the evaluator still runs for diagnostics.
            result.run_validity = RunValidity.INVALID_TREATMENT_DRIFT
            result.invalid_reason = "treatment drift: " + "; ".join(invariant["violations"])
        if config == "C2":
            self._capture_c2(result, store, cond)
        else:
            self._capture_invocation(result, store, outcome, prefix="")

        # 4. EVALUATE --------------------------------------------------------------
        # On an infrastructure stop (auth/limit/harness) or a C2 protocol violation there is no
        # task result to score; skip evaluation (acceptance stays not_run) but capture + clean up.
        if not infra_stop:
            _evaluate_and_record(evaluator, wc.path, store, result)

        # 5. CAPTURE RESULTS (manifest + result) -----------------------------------
        # run_validity stays VALID unless set above; a task fail is a valid outcome.
        return self._finalize(result, store, manifest, t0, wc, session, cleanup_runner)

    # ---------------------------------------------------------------- capture ----
    @staticmethod
    def _capture_invocation(result, store, outcome, prefix: str) -> None:
        """Write one invocation's stdout/stderr/events/process under ``prefix`` and point the
        result's artifact refs at them (for C2: the last executed phase)."""
        import json as _json

        # G12: agent output is untrusted text -> write_safe (withheld, never raised; the result
        # ref still points at the file, which is a placeholder when its content was withheld).
        def put(attr, name, content):
            if store.write_safe(name, content)["status"] != "write_failed" and attr:
                setattr(result.artifacts, attr, store.ref(name))

        if outcome.stdout:
            put("stdout", f"{prefix}stdout.txt", outcome.stdout)
        if outcome.stderr:
            put("stderr", f"{prefix}stderr.txt", outcome.stderr)
        if outcome.process is not None:
            put(None, f"{prefix}process.json", outcome.process)
        if outcome.events:
            put("events", f"{prefix}events.jsonl", "\n".join(_json.dumps(e) for e in outcome.events))

    def _capture_c2(self, result, store, cond) -> None:
        """Per-phase evidence in separate files; phase 2 never overwrites phase 1."""
        for rec in cond.phases:
            self._capture_invocation(result, store, rec.outcome, prefix=f"{rec.label}.")
        if cond.plan_text:
            store.write_safe("plan.txt", cond.plan_text)
        store.write_safe("c2.json", cond.c2_record())

    # ---------------------------------------------------------------- finalize --
    def _finalize(self, result, store, manifest, t0, wc, session, cleanup_runner) -> RunResult:
        result.ended_at = _utc_now()
        result.duration_seconds = round(time.monotonic() - t0, 6)

        # 6/7. PURGE + EXACT CLEANUP (after artifacts captured) --------------------
        plan = None
        try:
            plan = build_cleanup_plan(str(wc.path), [session.session_id],
                                      uid=self.uid, home=self.home.as_posix())
            report = cleanup_runner.execute(plan)
            performed = bool(report.get("executed", False))
        except Exception as exc:
            # never the exception message: it may quote untrusted text (G12)
            report, performed = {"error": type(exc).__name__, "cleanup_failed": True}, False

        # A Dry cleanup runner never actually removes anything by design (offline/test paths) --
        # only a real cleanup is held to the "must actually be clean" invariant below.
        real_cleanup = not isinstance(cleanup_runner, DryCleanupRunner)
        residue = verify_residue(plan, home=self.home.as_posix()) if (real_cleanup and plan is not None) else None
        if residue is not None:
            report["residue"] = residue
        if real_cleanup and (not performed or (residue is not None and not residue["all_clear"])) \
                and result.run_validity is RunValidity.VALID:
            result.run_validity = RunValidity.INVALID_HARNESS
            result.harness_failure = True
            result.invalid_reason = "cleanup_failed: " + _cleanup_failure_detail(report, residue)

        cleanup_entry = store.write_safe("cleanup.json", report)
        result.cleanup = CleanupRef(
            performed=performed,
            report_ref=None if cleanup_entry["status"] == "write_failed" else store.ref("cleanup.json"))

        # 8. FINALIZE (G12): one place decides whether the persisted evidence is still sufficient.
        # Withheld content (placeholder + artifact_report.json) keeps the attempt auditable and
        # changes nothing; evidence that could not be stored at all makes the attempt invalid.
        failed = store.write_failures()
        if failed and result.run_validity is RunValidity.VALID:
            result.run_validity = RunValidity.INVALID_HARNESS
            result.harness_failure = True
            result.invalid_reason = "artifact_write_failed: " + ", ".join(sorted(failed))
        if store.report:
            entry = store.write_safe("artifact_report.json",
                                     {"entries": store.report, "hash_of_withheld_content": None})
            if entry["status"] != "write_failed":
                result.artifacts.artifact_report = store.ref("artifact_report.json")
        for name, content in (("manifest.json", manifest.to_dict()), ("result.json", result.to_dict())):
            if store.write_safe(name, content)["status"] == "write_failed":
                raise ArtifactFinalizationError(f"required run record {name} could not be persisted "
                                                f"(cleanup already ran)")
        # DONE
        return result


def _evaluate_and_record(evaluator, wc_path, store, result) -> None:
    """The single evaluation step (G8): run the evaluator once, record an auditable
    ``evaluator.json`` and copy the verdict axes onto the result.

    * the evaluator raising is an evaluator infrastructure error (never a crash, never retried);
    * if the record trips the artifact secret scan, only the offending diagnostic strings are
      withheld (size-only placeholder, ``output_withheld``); the verdict itself stands;
    * if even that cannot be written, a metadata-only record is written and the verdict becomes
      an evaluator error -- never a verdict without an auditable record.
    Validity is untouched (PILOT_PLAN §10); countability follows from
    ``status.derive_analysis_eligibility`` (``not_countable:evaluation_pending`` on error).
    """
    try:
        ev = evaluator.evaluate(wc_path)
    except Exception as exc:  # evaluator infrastructure failure, not a task outcome
        ev = EvaluationResult(Acceptance.ERROR, Regression.ERROR, evaluator_error=True,
                              detail=f"evaluator raised {type(exc).__name__}: {exc}")
    record = ev.to_dict()
    ref = store.ref("evaluator.json")
    try:
        try:
            store.write_json("evaluator.json", record)
        except ArtifactSecretError:
            record = withhold_markers(record, store.extra_secret_markers)   # shared with G12
            record["output_withheld"] = True
            try:
                store.write_json("evaluator.json", record)
            except ArtifactSecretError:
                ev = EvaluationResult(Acceptance.ERROR, Regression.ERROR, integrity=ev.integrity,
                                      evaluator_error=True,
                                      detail="evaluator record could not be finalized (secret scan)")
                store.write_json("evaluator.json", {**ev.to_dict(), "output_withheld": True,
                                                    "finalization_failed": True})
    except OSError as exc:
        # G12: storage failure (not a content decision) -> no auditable verdict; recorded and
        # turned into invalid:harness by _finalize's required-evidence rule.
        store.report.append({"name": "evaluator.json", "status": "write_failed",
                             "reason": WRITE_FAILED, "size_bytes": None, "content_withheld": False,
                             "error_type": type(exc).__name__})
        ev = EvaluationResult(Acceptance.ERROR, Regression.ERROR, integrity=ev.integrity,
                              evaluator_error=True, detail="evaluator record could not be stored")
        ref = None
    result.acceptance = ev.acceptance
    result.regression = ev.regression
    result.integrity = ev.integrity
    result.evaluator_error = ev.evaluator_error
    result.artifacts.evaluator = ref


def _cleanup_failure_detail(report: dict, residue: Optional[dict]) -> str:
    """Short, harness-controlled (never agent-controlled) summary for ``invalid_reason``."""
    parts = []
    if report.get("error"):
        parts.append(f"error={report['error']}")
    for c in report.get("commands", []):
        if not c.get("ok", True):
            parts.append(f"command_failed:{c.get('purpose', c.get('argv'))}")
    if residue is not None:
        for t in residue["targets"]:
            if not t["clear"]:
                parts.append(f"residue:{t['purpose']}")
    return "; ".join(parts) if parts else "cleanup did not report success"


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
