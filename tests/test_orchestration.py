"""G2 + G9: real C0/C1/C2 execution paths through RunLifecycle, fully offline (no claude/srt).

Scripted runners stand in for the CLI; the lifecycle, orchestrator, preflight, treatment
materialization, envelopes, session flags and artifact capture are the real code.
"""

import json
from pathlib import Path

import pytest
from _helpers import (TEST_APPROVAL, TEST_CLAUDE_MD, TEST_STATEMENT, TEST_WRAPPER,
                      make_treated_manifest, make_treatment)

from codeagent_configlab.envelope import implementation_envelope, planning_envelope
from codeagent_configlab.evaluator import SmokeEvaluator
from codeagent_configlab.lifecycle import AgentRunOutcome, DryCleanupRunner, RunLifecycle
from codeagent_configlab.preflight import _project_slug
from codeagent_configlab.process_control import Deadline, EXITED, ProcessRunResult
from codeagent_configlab.runners import RealAgentRunner
from codeagent_configlab.session import SessionSpec
from codeagent_configlab.status import (Acceptance, AgentOutcome, C2Protocol, RunValidity)

UUID = "66666666-7777-8888-9999-000000000000"


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _events(sid, result_text=None):
    res = {"type": "result", "subtype": "success", "is_error": False, "session_id": sid}
    if result_text is not None:
        res["result"] = result_text
    return [{"type": "system", "subtype": "init", "session_id": sid}, res]


def step(*, sid=None, outcome=AgentOutcome.COMPLETED, exit_code=0, mutate=None, advance=0.0,
         clock=None, result_text=None, events=None, inspect=None):
    """One scripted invocation."""
    def _run(wc, env, session, prompt, deadline):
        if inspect:
            inspect(wc)
        if mutate:
            mutate(wc.path)
        if clock is not None:
            clock.t += advance
        ev = events if events is not None else _events(sid or session.session_id, result_text)
        return AgentRunOutcome(exit_code=exit_code, session_id=sid or session.session_id,
                               agent_outcome=outcome, stdout=f"out-{session.mode}",
                               stderr="", events=ev, detail=f"scripted {outcome.value}")
    return _run


class ScriptedRunner:
    def __init__(self, *steps):
        self.steps, self.calls = list(steps), []

    def run(self, working_copy, envelope, session, *, prompt=None, deadline="UNSET"):
        self.calls.append({"envelope": envelope, "session": session, "prompt": prompt,
                           "deadline": deadline})
        return self.steps[len(self.calls) - 1](working_copy, envelope, session, prompt, deadline)


def _pristine(tmp_path):
    p = tmp_path / "pristine"
    p.mkdir()
    (p / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    return p


def _add_multiply(wc: Path):
    f = wc / "calc.py"
    f.write_text(f.read_text() + "\n\ndef multiply(a, b):\n    return a * b\n", encoding="utf-8")


def _run(tmp_path, config, runner, *, treatment="default", statement=TEST_STATEMENT, budget=None,
         clock=None, envelope=None, manifest=None):
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True, exist_ok=True)
    life = RunLifecycle(pristine=_pristine(tmp_path), runs_root=tmp_path / "runs",
                        results_root=tmp_path / "results", home=home)
    manifest = manifest or make_treated_manifest(config)
    kw = {"clock": clock} if clock is not None else {}
    result = life.execute(
        manifest=manifest, envelope=envelope or implementation_envelope(config),
        session=SessionSpec("new", UUID), evaluator=SmokeEvaluator(), agent_runner=runner,
        cleanup_runner=DryCleanupRunner(),
        treatment=make_treatment(config) if treatment == "default" else treatment,
        task_statement=statement, budget_seconds=budget, **kw,
    )
    run_dir = tmp_path / "results" / manifest.run_id
    return result, run_dir, home


def _json(run_dir, name):
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- A. C2 happy path --------

def test_a_c2_two_phases_one_run(tmp_path):
    runner = ScriptedRunner(step(result_text="PLAN: add multiply"), step(mutate=_add_multiply))
    result, run_dir, _ = _run(tmp_path, "C2", runner)

    assert len(runner.calls) == 2                               # two invocations ...
    assert len(list(run_dir.glob("result.json"))) == 1          # ... one experimental run
    p1, p2 = runner.calls
    assert p1["envelope"] == planning_envelope() and p1["session"] == SessionSpec("new", UUID)
    assert p1["prompt"] == TEST_WRAPPER.replace("{{TASK_STATEMENT}}", TEST_STATEMENT)
    assert p2["envelope"] == implementation_envelope("C2") and p2["session"] == SessionSpec("resume", UUID)
    assert p2["prompt"] == TEST_APPROVAL                        # fixed text, not plan-dependent

    assert result.run_validity is RunValidity.VALID
    assert result.c2_protocol is C2Protocol.OK
    assert result.session_continuity_verified is True
    assert result.phase1_exit_code == 0 and result.phase2_exit_code == 0
    assert result.acceptance is Acceptance.PASS
    assert result.validate() == []

    c2 = _json(run_dir, "c2.json")
    assert c2["invocations"] == 2
    assert [p["label"] for p in c2["phases"]] == ["phase1", "phase2"]
    assert [p["session_flag"] for p in c2["phases"]] == ["--session-id", "--resume"]
    assert c2["phase1_readonly"]["ok"] is True
    assert (run_dir / "plan.txt").read_text() == "PLAN: add multiply"
    assert (run_dir / "phase1.events.jsonl").exists() and (run_dir / "phase2.events.jsonl").exists()
    assert (run_dir / "phase1.stdout.txt").read_text() == "out-new"
    assert (run_dir / "phase2.stdout.txt").read_text() == "out-resume"   # not overwritten
    assert result.artifacts.events == "phase2.events.jsonl"


# ---------------------------------------------------------------- B. phase-1 writes -------

def test_b_phase1_repository_mutation_is_protocol_violation(tmp_path):
    runner = ScriptedRunner(step(mutate=_add_multiply), step())
    result, run_dir, _ = _run(tmp_path, "C2", runner)
    assert len(runner.calls) == 1                               # phase 2 never started
    assert result.c2_protocol is C2Protocol.PHASE1_WRITE
    assert result.run_validity is RunValidity.INVALID_C2_PROTOCOL
    assert result.acceptance is Acceptance.NOT_RUN              # not scored as a task outcome
    assert _json(run_dir, "c2.json")["phase1_readonly"]["changed_paths"] == ["calc.py"]
    assert result.validate() == []


def test_b_phase1_git_or_seeded_settings_write_also_detected(tmp_path):
    def touch_settings(wc):
        (wc / ".claude" / "settings.json").write_text('{"x": 1}', encoding="utf-8")
    runner = ScriptedRunner(step(mutate=touch_settings), step())
    result, _, _ = _run(tmp_path, "C2", runner)
    assert result.c2_protocol is C2Protocol.PHASE1_WRITE and len(runner.calls) == 1


def test_b_phase1_pycache_is_the_only_exclusion(tmp_path):
    def cache(wc):
        (wc / "__pycache__").mkdir()
        (wc / "__pycache__" / "calc.cpython-314.pyc").write_bytes(b"x")
    runner = ScriptedRunner(step(mutate=cache), step())
    result, _, _ = _run(tmp_path, "C2", runner)
    assert result.c2_protocol is C2Protocol.OK and len(runner.calls) == 2


def test_b_phase1_auto_memory_write_is_protocol_violation(tmp_path):
    home = tmp_path / "home"

    def write_memory(wc):
        mem = home / ".claude" / "projects" / _project_slug(wc) / "memory"
        mem.mkdir(parents=True)
        (mem / "note.md").write_text("remember", encoding="utf-8")
    runner = ScriptedRunner(step(mutate=write_memory), step())
    result, run_dir, _ = _run(tmp_path, "C2", runner)
    assert result.c2_protocol is C2Protocol.PHASE1_WRITE and len(runner.calls) == 1
    assert _json(run_dir, "c2.json")["phase1_readonly"]["project_state_extra"] == ["memory"]


def test_b_transcript_and_empty_memory_are_allowed(tmp_path):
    home = tmp_path / "home"

    def claude_state(wc):
        proj = home / ".claude" / "projects" / _project_slug(wc)
        (proj / "memory").mkdir(parents=True)
        (proj / f"{UUID}.jsonl").write_text("{}", encoding="utf-8")
    runner = ScriptedRunner(step(mutate=claude_state), step())
    result, _, _ = _run(tmp_path, "C2", runner)
    assert result.c2_protocol is C2Protocol.OK and len(runner.calls) == 2


def test_b_phase1_user_level_instruction_write_is_protocol_violation(tmp_path):
    home = tmp_path / "home"
    runner = ScriptedRunner(step(mutate=lambda wc: (home / ".claude" / "CLAUDE.md").write_text("x")), step())
    result, _, _ = _run(tmp_path, "C2", runner)
    assert result.c2_protocol is C2Protocol.PHASE1_WRITE and len(runner.calls) == 1


# ---------------------------------------------------------------- C. session identity -----

def test_c_phase1_session_mismatch(tmp_path):
    runner = ScriptedRunner(step(sid="11111111-0000-0000-0000-000000000000"), step())
    result, _, _ = _run(tmp_path, "C2", runner)
    assert len(runner.calls) == 1
    assert result.c2_protocol is C2Protocol.PHASE_TRANSITION_FAILED
    assert result.run_validity is RunValidity.INVALID_C2_PROTOCOL
    assert result.session_continuity_verified is False


def test_c_phase2_session_mismatch(tmp_path):
    runner = ScriptedRunner(step(), step(sid="22222222-0000-0000-0000-000000000000", mutate=_add_multiply))
    result, _, _ = _run(tmp_path, "C2", runner)
    assert len(runner.calls) == 2
    assert result.c2_protocol is C2Protocol.PHASE_TRANSITION_FAILED
    assert result.run_validity is RunValidity.INVALID_C2_PROTOCOL
    assert result.acceptance is Acceptance.NOT_RUN


def test_c_completed_phase_without_session_evidence_is_not_trusted(tmp_path):
    runner = ScriptedRunner(step(events=[]), step())
    result, _, _ = _run(tmp_path, "C2", runner)
    assert result.c2_protocol is C2Protocol.PHASE_TRANSITION_FAILED and len(runner.calls) == 1


# ---------------------------------------------------------------- D/E. shared budget ------

def test_d_phase2_gets_only_the_remaining_budget(tmp_path):
    clock = FakeClock()
    runner = ScriptedRunner(step(clock=clock, advance=8.0), step(clock=clock, advance=1.0))
    result, run_dir, _ = _run(tmp_path, "C2", runner, budget=10.0, clock=clock)
    d1, d2 = runner.calls[0]["deadline"], runner.calls[1]["deadline"]
    assert isinstance(d1, Deadline) and d1.budget_seconds == 10.0
    assert isinstance(d2, Deadline) and d2.budget_seconds == pytest.approx(2.0)
    phases = _json(run_dir, "c2.json")["phases"]
    assert [p["budget_seconds"] for p in phases] == [10.0, pytest.approx(2.0)]
    assert result.run_validity is RunValidity.VALID


def test_e_budget_exhausted_in_phase1_is_valid_timeout(tmp_path):
    clock = FakeClock()
    runner = ScriptedRunner(step(clock=clock, advance=10.0, outcome=AgentOutcome.TIMEOUT, exit_code=None,
                                 events=[{"type": "system", "subtype": "init", "session_id": UUID}]),
                            step())
    result, _, _ = _run(tmp_path, "C2", runner, budget=10.0, clock=clock)
    assert len(runner.calls) == 1                               # phase 2 never started
    assert result.agent_outcome is AgentOutcome.TIMEOUT
    assert result.run_validity is RunValidity.VALID             # G1 semantics inherited
    assert result.c2_protocol is C2Protocol.OK
    assert result.phase1_exit_code is None and result.phase2_exit_code is None
    assert result.acceptance is Acceptance.FAIL                 # final state still evaluated


def test_e_phase1_finishing_exactly_at_the_cap_does_not_start_phase2(tmp_path):
    clock = FakeClock()
    runner = ScriptedRunner(step(clock=clock, advance=10.0), step())
    result, _, _ = _run(tmp_path, "C2", runner, budget=10.0, clock=clock)
    assert len(runner.calls) == 1
    assert result.agent_outcome is AgentOutcome.TIMEOUT and result.run_validity is RunValidity.VALID


def test_e_c2_without_budget_passes_explicit_no_cap_to_both_phases(tmp_path):
    runner = ScriptedRunner(step(), step())
    _run(tmp_path, "C2", runner, budget=None)
    assert [c["deadline"] for c in runner.calls] == [None, None]  # never a per-phase fallback cap


def test_e_phase1_error_exit_ends_run_without_phase2(tmp_path):
    runner = ScriptedRunner(step(outcome=AgentOutcome.ERROR_EXIT, exit_code=2), step())
    result, _, _ = _run(tmp_path, "C2", runner)
    assert len(runner.calls) == 1
    assert result.agent_outcome is AgentOutcome.ERROR_EXIT
    assert result.run_validity is RunValidity.VALID and result.phase1_exit_code == 2


def test_e_phase1_auth_failure_keeps_infrastructure_class(tmp_path):
    runner = ScriptedRunner(step(outcome=AgentOutcome.AUTH_FAILURE, exit_code=1), step())
    result, _, _ = _run(tmp_path, "C2", runner)
    assert len(runner.calls) == 1 and result.run_validity is RunValidity.INVALID_INFRASTRUCTURE


# ---------------------------------------------------------------- C0 / C1 paths -----------

def test_c1_one_invocation_with_exact_treatment(tmp_path):
    seen = {}
    runner = ScriptedRunner(step(mutate=_add_multiply,
                                 inspect=lambda wc: seen.update(md=(wc.path / "CLAUDE.md").read_bytes())))
    result, run_dir, _ = _run(tmp_path, "C1", runner)
    assert len(runner.calls) == 1
    assert runner.calls[0]["envelope"] == implementation_envelope("C1")
    assert runner.calls[0]["prompt"] == TEST_STATEMENT          # same statement bytes as C0
    assert seen["md"] == TEST_CLAUDE_MD
    assert result.run_validity is RunValidity.VALID and result.c2_protocol is C2Protocol.NOT_APPLICABLE
    cf = _json(run_dir, "changed_files.json")
    assert (cf["added"], cf["modified"], cf["deleted"]) == ([], ["calc.py"], [])  # treatment not "added"
    t = _json(run_dir, "treatment.json")
    assert t["ok"] is True and t["start"]["CLAUDE.md"] == t["expected_start"]["CLAUDE.md"]


def test_c0_one_invocation_without_treatment(tmp_path):
    seen = {}
    runner = ScriptedRunner(step(inspect=lambda wc: seen.update(md=(wc.path / "CLAUDE.md").exists())))
    result, _, _ = _run(tmp_path, "C0", runner)
    assert len(runner.calls) == 1 and seen["md"] is False
    assert runner.calls[0]["prompt"] == TEST_STATEMENT
    assert result.run_validity is RunValidity.VALID


def test_c1_treatment_drift_is_recorded_not_hidden(tmp_path):
    def edit_md(wc):
        (wc / "CLAUDE.md").write_bytes(b"agent rewrote this\n")
    runner = ScriptedRunner(step(mutate=edit_md))
    result, run_dir, _ = _run(tmp_path, "C1", runner)
    t = _json(run_dir, "treatment.json")
    assert t["ok"] is False and t["violations"] == ["modified CLAUDE.md"]
    assert "CLAUDE.md" in _json(run_dir, "changed_files.json")["modified"]
    assert result.run_validity is RunValidity.INVALID_TREATMENT_DRIFT
    assert result.acceptance is not Acceptance.NOT_RUN          # diagnostic evaluation still ran
    wc = next((tmp_path / "runs").iterdir())
    assert (wc / "CLAUDE.md").read_bytes() == b"agent rewrote this\n"   # not restored


@pytest.mark.parametrize("config,treatment", [
    ("C1", None),                                                     # missing
    ("C2", None),
    ("C1", "wrong-md"),                                               # hash mismatch vs manifest
    ("C2", "wrong-approval"),
    ("C0", "c1-material"),                                            # C0 must get none
])
def test_bad_treatment_is_preflight_failure_before_any_invocation(tmp_path, config, treatment):
    from codeagent_configlab.treatment import Treatment
    bad = {
        None: None,
        "wrong-md": Treatment(claude_md=b"something else\n"),
        "wrong-approval": Treatment(claude_md=TEST_CLAUDE_MD, planning_wrapper=TEST_WRAPPER,
                                    approval_message="different approval\n"),
        "c1-material": Treatment(claude_md=TEST_CLAUDE_MD),
    }[treatment]
    runner = ScriptedRunner(step(), step())
    result, _, _ = _run(tmp_path, config, runner, treatment=bad)
    assert runner.calls == []
    assert result.run_validity is RunValidity.PREFLIGHT_FAILED


def test_statement_not_matching_manifest_is_preflight_failure(tmp_path):
    runner = ScriptedRunner(step())
    result, _, _ = _run(tmp_path, "C0", runner, statement="a different statement")
    assert runner.calls == [] and result.run_validity is RunValidity.PREFLIGHT_FAILED


def test_non_standard_implementation_envelope_is_rejected(tmp_path):
    runner = ScriptedRunner(step())
    result, _, _ = _run(tmp_path, "C1", runner, envelope=planning_envelope())
    assert runner.calls == []
    assert result.run_validity is RunValidity.INVALID_HARNESS


# ---------------------------------------------------------------- I. envelope equality ----

def test_i_envelope_used_by_lifecycle_is_identical_for_c0_c1_c2_phase2(tmp_path):
    used = {}
    for config in ("C0", "C1", "C2"):
        runner = ScriptedRunner(step(), step())
        _run(tmp_path / config, config, runner)
        used[config] = runner.calls[-1]["envelope"]
    assert used["C0"] == used["C1"] == used["C2"]
    assert used["C0"].identity_dict() == used["C2"].identity_dict()
    assert used["C0"].envelope_hash() == used["C1"].envelope_hash() == used["C2"].envelope_hash()


class ArgvSpawn:
    """Fake run_with_deadline: records argv + rendered outer srt config; echoes the session id."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kw):
        cfg = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        self.calls.append({"argv": list(argv), "cwd": kw["cwd"], "cfg": cfg,
                           "tmp": str(Path(argv[2]).parent), "env": dict(kw["env"])})
        flag = "--session-id" if "--session-id" in argv else "--resume"
        sid = argv[argv.index(flag) + 1]
        out = "\n".join(json.dumps(e) for e in _events(sid)).encode()
        return ProcessRunResult(termination=EXITED, timed_out=False, returncode=0, stdout=out)


def _normalized(call, uuid):
    def norm(s: str) -> str:
        for token, name in ((call["cwd"], "<WC>"), (call["tmp"], "<TMP>"), (uuid, "<UUID>")):
            s = s.replace(json.dumps(token)[1:-1], name).replace(token, name)
        return s
    argv = [norm(a) for a in call["argv"]]
    cfg = json.loads(norm(json.dumps(call["cfg"])))
    return argv, cfg


def test_i_real_runner_argv_and_sandbox_equal_across_c0_c1_c2_phase2(tmp_path):
    captured, raw = {}, {}
    for config in ("C0", "C1", "C2"):
        spawn = ArgvSpawn()
        runner = RealAgentRunner(home=str(tmp_path / "home"), harness_root=str(tmp_path / "hr"),
                                 model="MODEL-UNDER-TEST", effort="high", prompt="unused",
                                 spawn=spawn, tmp_root=str(tmp_path / config / "tmp"),
                                 srt_path="/srt", claude_path="/claude")
        result, _, _ = _run(tmp_path / config, config, runner)
        assert result.run_validity is RunValidity.VALID, result.invalid_reason
        captured[config] = [_normalized(c, UUID) for c in spawn.calls]
        raw[config] = spawn.calls

    # G11: every invocation (C0, C1, C2 phase 1, C2 phase 2) loads instructions the same way
    for config in ("C0", "C1", "C2"):
        for argv, cfg in captured[config]:
            assert argv[argv.index("--add-dir") + 1] == "<WC>"
            assert argv[argv.index("--setting-sources") + 1] == ""
            assert "<WC>/.claude" in cfg["filesystem"]["denyWrite"] or cfg["filesystem"]["denyWrite"] == ["<WC>"]
    assert {e["env"].get("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD") for c in raw.values() for e in c} == {"1"}
    c0_argv, c0_cfg = captured["C0"][0]
    c1_argv, c1_cfg = captured["C1"][0]
    (p1_argv, p1_cfg), (p2_argv, p2_cfg) = captured["C2"]
    assert c0_argv == c1_argv and c0_cfg == c1_cfg
    # C2 phase 2 == C0/C1 except the session flag (resume the phase-1 session)
    i = p2_argv.index("--resume")
    assert p2_argv[:i] + ["--session-id"] + p2_argv[i + 1:] == c0_argv
    assert p2_cfg == c0_cfg
    # C2 phase 1 differs only in the tool list and the read-only working copy
    diffs = [(a, b) for a, b in zip(p1_argv, c0_argv) if a != b]
    assert diffs == [("Bash,Read,Glob,Grep", "Bash,Read,Edit,Write,Glob,Grep")]
    assert len(p1_argv) == len(c0_argv)
    assert p1_cfg["network"] == c0_cfg["network"]
    assert p1_cfg["filesystem"]["denyWrite"] == ["<WC>"] and "<WC>" not in p1_cfg["filesystem"]["allowWrite"]
    assert {k: v for k, v in p1_cfg["filesystem"].items() if k not in ("allowWrite", "denyWrite")} == \
           {k: v for k, v in c0_cfg["filesystem"].items() if k not in ("allowWrite", "denyWrite")}
