"""End-to-end lifecycle wiring, fully offline (no claude/srt/network)."""

from pathlib import Path
from unittest import mock

from _helpers import TEST_STATEMENT, make_manifest, make_treated_manifest, make_treatment

from codeagent_configlab.envelope import implementation_envelope
from codeagent_configlab.evaluator import SmokeEvaluator
from codeagent_configlab.lifecycle import DryAgentRunner, DryCleanupRunner, RunLifecycle
from codeagent_configlab.session import SessionSpec
from codeagent_configlab.status import Acceptance, RunValidity, C2Protocol


def _smoke_pristine(tmp_path: Path) -> Path:
    p = tmp_path / "pristine"
    p.mkdir()
    (p / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    return p


def _add_multiply(wc: Path) -> None:
    f = wc / "calc.py"
    f.write_text(f.read_text() + "\n\ndef multiply(a, b):\n    return a * b\n", encoding="utf-8")


def test_full_lifecycle_valid_resolved_run(tmp_path):
    pristine = _smoke_pristine(tmp_path)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    manifest = make_manifest("C0")
    session = SessionSpec("new", "11111111-1111-1111-1111-111111111111")

    result = life.execute(
        manifest=manifest,
        envelope=implementation_envelope("C0"),
        session=session,
        evaluator=SmokeEvaluator(),
        agent_runner=DryAgentRunner(mutate=_add_multiply),
        cleanup_runner=DryCleanupRunner(),
    )

    assert result.run_validity is RunValidity.VALID
    assert result.acceptance is Acceptance.PASS
    assert result.agent_exit_code == 0
    assert result.validate() == []  # the result document is schema-valid

    run_dir = (tmp_path / "results") / manifest.run_id
    for name in ("manifest.json", "result.json", "changed_files.json", "evaluator.json", "cleanup.json"):
        assert (run_dir / name).exists(), name


def test_lifecycle_task_failure_is_valid(tmp_path):
    pristine = _smoke_pristine(tmp_path)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    manifest = make_manifest("C0")
    # agent does NOT add multiply -> acceptance fail, but the run is still VALID
    result = life.execute(
        manifest=manifest,
        envelope=implementation_envelope("C0"),
        session=SessionSpec("new", "22222222-2222-2222-2222-222222222222"),
        evaluator=SmokeEvaluator(),
        agent_runner=DryAgentRunner(mutate=None),
    )
    assert result.run_validity is RunValidity.VALID
    assert result.acceptance is Acceptance.FAIL


def test_c2_sets_protocol_ok_on_continuity(tmp_path):
    pristine = _smoke_pristine(tmp_path)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    manifest = make_treated_manifest("C2")
    result = life.execute(
        manifest=manifest,
        envelope=implementation_envelope("C2"),
        session=SessionSpec("new", "33333333-3333-3333-3333-333333333333"),
        evaluator=SmokeEvaluator(),
        agent_runner=DryAgentRunner(),
        treatment=make_treatment("C2"),
        task_statement=TEST_STATEMENT,
    )
    assert result.c2_protocol is C2Protocol.OK


def test_results_dir_has_no_secret_markers(tmp_path):
    from codeagent_configlab.artifacts import ArtifactStore

    pristine = _smoke_pristine(tmp_path)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    manifest = make_treated_manifest("C1")
    result = life.execute(
        manifest=manifest,
        envelope=implementation_envelope("C1"),
        session=SessionSpec("new", "44444444-4444-4444-4444-444444444444"),
        evaluator=SmokeEvaluator(),
        agent_runner=DryAgentRunner(mutate=_add_multiply),
        treatment=make_treatment("C1"),
        task_statement=TEST_STATEMENT,
    )
    assert result.run_validity is RunValidity.VALID
    store = ArtifactStore(run_dir=(tmp_path / "results") / manifest.run_id)
    assert store.scan_dir_for_secrets() == {}


def test_preflight_failure_stops_run(tmp_path):
    # a CLAUDE.md above the runs root makes every WC ancestor-contaminated -> preflight_failed
    pristine = _smoke_pristine(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("x", encoding="utf-8")
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    manifest = make_manifest("C0")
    result = life.execute(
        manifest=manifest,
        envelope=implementation_envelope("C0"),
        session=SessionSpec("new", "55555555-5555-5555-5555-555555555555"),
        evaluator=SmokeEvaluator(),
        agent_runner=DryAgentRunner(mutate=_add_multiply),
    )
    assert result.run_validity is RunValidity.PREFLIGHT_FAILED


# --- G1: a correctly enforced cap is a valid outcome; a failed termination is not ----------

class _CannedRunner:
    def __init__(self, outcome):
        self.outcome = outcome

    def run(self, working_copy, envelope, session):
        return self.outcome


def _run_with(tmp_path, outcome):
    import json
    from codeagent_configlab.lifecycle import AgentRunOutcome  # noqa: F401 (type used by caller)

    life = RunLifecycle(pristine=_smoke_pristine(tmp_path), runs_root=tmp_path / "runs",
                        results_root=tmp_path / "results")
    manifest = make_manifest("C0")
    result = life.execute(manifest=manifest, envelope=implementation_envelope("C0"),
                          session=SessionSpec("new", "55555555-5555-5555-5555-555555555555"),
                          evaluator=SmokeEvaluator(), agent_runner=_CannedRunner(outcome),
                          cleanup_runner=DryCleanupRunner())
    run_dir = tmp_path / "results" / manifest.run_id
    stored = json.loads((run_dir / "result.json").read_text())
    return result, run_dir, stored


def test_agent_timeout_is_valid_and_evaluated(tmp_path):
    from codeagent_configlab.lifecycle import AgentRunOutcome
    from codeagent_configlab.status import AgentOutcome

    outcome = AgentRunOutcome(
        exit_code=None, session_id="55555555-5555-5555-5555-555555555555",
        agent_outcome=AgentOutcome.TIMEOUT, stdout="partial", events=[],
        detail="wall-clock cap of 60.0s reached; run-owned process tree terminated",
        process={"termination": "timeout_terminated", "timed_out": True, "returncode": None},
    )
    result, run_dir, stored = _run_with(tmp_path, outcome)
    assert result.run_validity is RunValidity.VALID
    assert result.harness_failure is False and result.invalid_reason is None
    assert stored["agent_outcome"] == "timeout"
    assert stored["agent_exit_code"] is None
    assert "cap" in stored["interruption_reason"]
    assert result.acceptance is Acceptance.FAIL        # evaluator ran on the final state
    assert (run_dir / "process.json").exists() and (run_dir / "stdout.txt").exists()
    assert result.validate() == []


def test_termination_failure_is_invalid_harness(tmp_path):
    from codeagent_configlab.lifecycle import AgentRunOutcome
    from codeagent_configlab.status import AgentOutcome

    outcome = AgentRunOutcome(
        exit_code=None, session_id=None, agent_outcome=AgentOutcome.HARNESS_ERROR,
        detail="process-tree termination failed: survivors; survivors=[4242]",
        process={"termination": "termination_failed", "survivors": [4242]},
    )
    result, run_dir, stored = _run_with(tmp_path, outcome)
    assert stored["run_validity"] == "invalid:harness"
    assert stored["harness_failure"] is True
    assert "termination failed" in stored["invalid_reason"]
    assert stored["acceptance"] == "not_run"
    assert (run_dir / "process.json").exists()
    assert result.validate() == []


# --------------------------------------------------------------- real cleanup wiring/invariant --

class _FakeCleanupRunner:
    """Non-Dry, in-process CleanupRunner double (no subprocess)."""

    def __init__(self, ok=True, leave_residue=False):
        self.ok = ok
        self.leave_residue = leave_residue
        self.calls = []

    def execute(self, plan):
        self.calls.append(plan)
        if self.leave_residue:
            for c in plan:
                if c.argv[:2] == ("rm", "-rf"):
                    Path(c.argv[-1]).mkdir(parents=True, exist_ok=True)
                    break
        return {"commands": [{"argv": list(c.argv), "exit": 0 if self.ok else 1, "ok": self.ok,
                              "purpose": c.purpose} for c in plan],
                "executed": self.ok, "cleanup_failed": not self.ok}


def _unsafe_build_cleanup_plan_for_tests(working_copy, session_uuids, *, uid, home):
    """Same argv shape as ``cleanup.build_cleanup_plan``, without its hardcoded-``/home/cclab``
    scope guard, so these tests can use a hermetic ``tmp_path``-based home instead of the real
    ``/home/cclab`` (which other tests in this file DO use by default -- but always with
    ``DryCleanupRunner``, which never executes anything for real)."""
    from codeagent_configlab.cleanup import CleanupCommand, wc_slug

    plan = [CleanupCommand(argv=("claude", "project", "purge", "-y", working_copy),
                           purpose="remove project transcripts/memory/config entry for this working copy")]
    for u in session_uuids:
        plan.append(CleanupCommand(argv=("rm", "-rf", "--", f"{home}/.claude/session-env/{u}"),
                                   purpose=f"remove exact session-env dir for {u}"))
    plan.append(CleanupCommand(argv=("rm", "-rf", "--", f"/tmp/claude/claude-{uid}/{wc_slug(working_copy)}"),
                               purpose="remove exact per-project /tmp/claude dir"))
    return plan


def test_real_cleanup_failure_is_invalid_harness(tmp_path):
    pristine = _smoke_pristine(tmp_path)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs",
                        results_root=tmp_path / "results", home=tmp_path / "home")
    manifest = make_manifest("C0")
    fake = _FakeCleanupRunner(ok=False)
    with mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan",
                    _unsafe_build_cleanup_plan_for_tests):
        result = life.execute(
            manifest=manifest, envelope=implementation_envelope("C0"),
            session=SessionSpec("new", "66666666-6666-6666-6666-666666666666"),
            evaluator=SmokeEvaluator(), agent_runner=DryAgentRunner(mutate=_add_multiply),
            cleanup_runner=fake,
        )
    assert len(fake.calls) == 1
    assert result.run_validity is RunValidity.INVALID_HARNESS
    assert result.harness_failure is True
    assert result.invalid_reason.startswith("cleanup_failed:")
    assert result.validate() == []


def test_real_cleanup_success_with_leftover_residue_is_invalid_harness(tmp_path):
    pristine = _smoke_pristine(tmp_path)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs",
                        results_root=tmp_path / "results", home=tmp_path / "home")
    manifest = make_manifest("C0")
    fake = _FakeCleanupRunner(ok=True, leave_residue=True)
    with mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan",
                    _unsafe_build_cleanup_plan_for_tests):
        result = life.execute(
            manifest=manifest, envelope=implementation_envelope("C0"),
            session=SessionSpec("new", "77777777-7777-7777-7777-777777777777"),
            evaluator=SmokeEvaluator(), agent_runner=DryAgentRunner(mutate=_add_multiply),
            cleanup_runner=fake,
        )
    assert result.run_validity is RunValidity.INVALID_HARNESS
    assert result.invalid_reason.startswith("cleanup_failed:")
    assert result.validate() == []


def test_real_cleanup_success_records_performed_true_and_stays_valid(tmp_path):
    pristine = _smoke_pristine(tmp_path)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs",
                        results_root=tmp_path / "results", home=tmp_path / "home")
    manifest = make_manifest("C0")
    fake = _FakeCleanupRunner(ok=True)
    with mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan",
                    _unsafe_build_cleanup_plan_for_tests):
        result = life.execute(
            manifest=manifest, envelope=implementation_envelope("C0"),
            session=SessionSpec("new", "88888888-8888-8888-8888-888888888888"),
            evaluator=SmokeEvaluator(), agent_runner=DryAgentRunner(mutate=_add_multiply),
            cleanup_runner=fake,
        )
    assert result.run_validity is RunValidity.VALID
    assert result.cleanup.performed is True
    assert result.validate() == []


def test_dry_cleanup_regression_guard_still_valid_despite_performed_false(tmp_path):
    # Existing behavior, unaffected by the new invariant: Dry cleanup's performed=False must
    # never be held to the "real cleanup must actually be clean" rule.
    pristine = _smoke_pristine(tmp_path)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    manifest = make_manifest("C0")
    result = life.execute(
        manifest=manifest, envelope=implementation_envelope("C0"),
        session=SessionSpec("new", "99999999-9999-9999-9999-999999999999"),
        evaluator=SmokeEvaluator(), agent_runner=DryAgentRunner(mutate=_add_multiply),
        cleanup_runner=DryCleanupRunner(),
    )
    assert result.run_validity is RunValidity.VALID
    assert result.cleanup.performed is False
    assert result.validate() == []
