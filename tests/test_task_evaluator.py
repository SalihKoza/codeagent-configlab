"""G5: real task evaluator -- copy-only, trusted restore, hidden injection, separate axes."""

import json
import os
import sys
from pathlib import Path

import pytest
from _helpers import TEST_STATEMENT, FakeSandbox, make_treated_manifest, make_treatment

from codeagent_configlab.envelope import implementation_envelope
from codeagent_configlab.lifecycle import AgentRunOutcome, DryCleanupRunner, RunLifecycle
from codeagent_configlab.orchestration import snapshot_tree
from codeagent_configlab.session import SessionSpec
from codeagent_configlab.status import Acceptance, AgentOutcome, Integrity, Regression, RunValidity
from codeagent_configlab.task_evaluator import (CheckSpec, TaskEvaluator, TaskEvaluatorSpec,
                                                evaluate_candidate, overlay_candidate)

PY = sys.executable
CANARY = "HIDDEN-CANARY-5e7d0c"
HEADER = "import os, sys\nsys.path.insert(0, os.getcwd())\nimport calc\n"


def _te(spec, sandbox=None):
    """G5 semantics under the offline identity wrapper (the real srt sandbox: test_evaluator_sandbox)."""
    return TaskEvaluator(spec, sandbox=sandbox or FakeSandbox())


def _ec(spec, state, sandbox=None):
    return evaluate_candidate(spec, state, sandbox or FakeSandbox())


def _task(tmp_path):
    """pristine fixture + hidden checks, in separate trees (hidden never inside pristine)."""
    pristine = tmp_path / "task" / "pristine"
    (pristine / "tests").mkdir(parents=True)
    (pristine / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (pristine / "tests" / "test_public.py").write_text(HEADER + "assert calc.add(2, 3) == 5\n")
    hidden = tmp_path / "task" / "hidden"
    hidden.mkdir()
    (hidden / "check_accept.py").write_text(f"# {CANARY}\n" + HEADER + "assert calc.multiply(3, 4) == 12\n")
    (hidden / "check_regress.py").write_text(HEADER + "assert calc.add(-1, 1) == 0\n")
    return pristine, hidden


def _spec(pristine, hidden, **kw):
    base = dict(
        pristine=pristine, hidden_dir=hidden,
        protected_paths=("tests/test_public.py", "conftest.py"),
        acceptance=(CheckSpec("hidden-accept", (PY, "_hidden_tests/check_accept.py"), 60),),
        regression=(CheckSpec("public", (PY, "tests/test_public.py"), 60),
                    CheckSpec("hidden-regress", (PY, "_hidden_tests/check_regress.py"), 60)),
    )
    base.update(kw)
    return TaskEvaluatorSpec(**base)


def _state(tmp_path, pristine, name, calc=None, public=None, extra=None):
    d = overlay_candidate(pristine, None, tmp_path / "states" / name)
    if calc is not None:
        (d / "calc.py").write_text(calc, encoding="utf-8")
    if public is not None:
        (d / "tests" / "test_public.py").write_text(public)
    for rel, text in (extra or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text)
    return d


GOOD = "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"


def test_offline_validity_states_pristine_reference_known_wrong(tmp_path):
    pristine, hidden = _task(tmp_path)
    spec = _spec(pristine, hidden)
    res_pristine = _ec(spec, _state(tmp_path, pristine, "pristine"))
    assert (res_pristine.acceptance, res_pristine.regression) == (Acceptance.FAIL, Regression.PASS)
    ref = tmp_path / "reference"
    ref.mkdir()
    (ref / "calc.py").write_text(GOOD)
    res_ref = _ec(spec, overlay_candidate(pristine, ref, tmp_path / "states" / "ref"))
    assert (res_ref.acceptance, res_ref.regression) == (Acceptance.PASS, Regression.PASS)
    wrong = _state(tmp_path, pristine, "wrong",
                   calc="def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return 12\n")
    # hard-coded answer passes this one hidden check -- the gate needs a discriminating check;
    # here it is shown that the evaluator faithfully reports what its checks say.
    assert _ec(spec, wrong).acceptance is Acceptance.PASS
    wrong2 = _state(tmp_path, pristine, "wrong2",
                    calc="def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a + b\n")
    assert _ec(spec, wrong2).acceptance is Acceptance.FAIL
    assert not res_pristine.evaluator_error and not res_ref.evaluator_error


def test_j_canonical_state_untouched_only_the_copy_changes(tmp_path):
    pristine, hidden = _task(tmp_path)
    cand = _state(tmp_path, pristine, "c", calc=GOOD, public="assert True\n",
                  extra={"conftest.py": "raise SystemExit(0)\n"})
    before = snapshot_tree(cand, ignore_dirs=())
    marker = CheckSpec("writes", (PY, "-c", "open('EVAL_WAS_HERE', 'w').write('x')"), 30)
    res = _te(_spec(pristine, hidden, structural=(marker,))).evaluate(cand)
    assert snapshot_tree(cand, ignore_dirs=()) == before           # nothing restored/injected here
    assert not (cand / "EVAL_WAS_HERE").exists() and not (cand / "_hidden_tests").exists()
    assert res.acceptance is Acceptance.PASS


def test_k_m_protected_paths_restored_in_copy_and_weakened_tests_do_not_help(tmp_path):
    pristine, hidden = _task(tmp_path)
    # agent weakened the public test, planted a conftest, did NOT implement multiply
    cand = _state(tmp_path, pristine, "cheat", public="assert True\n",
                  extra={"conftest.py": "print('hijack')\n"})
    res = _te(_spec(pristine, hidden)).evaluate(cand)
    assert res.acceptance is Acceptance.FAIL                       # hidden acceptance still fails
    assert res.integrity is Integrity.PROTECTED_PATH_MODIFIED
    rec = {r["path"]: r for r in res.restoration}
    assert rec["tests/test_public.py"] == {"path": "tests/test_public.py", "agent_modified": True,
                                           "action": "restored"}
    assert rec["conftest.py"]["action"] == "removed" and rec["conftest.py"]["agent_modified"] is True
    # the canonical candidate still shows the agent's weakened test
    assert (cand / "tests" / "test_public.py").read_text() == "assert True\n"


def test_k_breaking_the_public_behavior_is_caught_by_the_restored_public_test(tmp_path):
    pristine, hidden = _task(tmp_path)
    cand = _state(tmp_path, pristine, "broken",
                  calc="def add(a, b):\n    return a - b\n\ndef multiply(a, b):\n    return a * b\n",
                  public=HEADER + "assert calc.add(2, 3) == -1\n")
    res = _te(_spec(pristine, hidden)).evaluate(cand)
    assert res.acceptance is Acceptance.PASS and res.regression is Regression.FAIL   # N: separate
    assert res.integrity is Integrity.PROTECTED_PATH_MODIFIED


def test_l_hidden_material_injected_only_into_the_copy(tmp_path):
    pristine, hidden = _task(tmp_path)
    cand = _state(tmp_path, pristine, "c", calc=GOOD)
    res = _te(_spec(pristine, hidden)).evaluate(cand)
    assert res.injected == ["check_accept.py", "check_regress.py"]
    assert not (cand / "_hidden_tests").exists()


def test_agent_planted_hidden_dest_is_replaced_and_flagged(tmp_path):
    pristine, hidden = _task(tmp_path)
    cand = _state(tmp_path, pristine, "plant", extra={"_hidden_tests/check_accept.py": "pass\n"})
    res = _te(_spec(pristine, hidden)).evaluate(cand)
    assert res.acceptance is Acceptance.FAIL
    assert any(r["action"] == "replaced_by_hidden" for r in res.restoration)
    assert res.integrity is Integrity.PROTECTED_PATH_MODIFIED


def test_o_evaluator_errors_are_distinct_from_task_failure(tmp_path):
    pristine, hidden = _task(tmp_path)
    cand = _state(tmp_path, pristine, "c", calc=GOOD)
    missing = _te(_spec(pristine, tmp_path / "nope")).evaluate(cand)
    assert missing.evaluator_error and missing.acceptance is Acceptance.ERROR
    # G5s: a check program that cannot be resolved is caught by the sandbox preflight, before any
    # command runs -> the whole evaluation is an evaluator error (was: only that check).
    bad_cmd = CheckSpec("bad", ("definitely-not-a-command-xyz",), 10)
    r = _te(_spec(pristine, hidden, acceptance=(bad_cmd,))).evaluate(cand)
    assert r.evaluator_error and r.acceptance is Acceptance.ERROR and r.regression is Regression.ERROR
    assert all(c["exit_code"] is None for c in r.checks)
    usage = CheckSpec("no-tests", (PY, "-c", "raise SystemExit(5)"), 10, error_codes=(5,))
    r = _te(_spec(pristine, hidden, regression=(usage,))).evaluate(cand)
    assert r.evaluator_error and r.regression is Regression.ERROR and r.acceptance is Acceptance.PASS
    # agent code that does not even import is a task failure, not an evaluator error
    broken = _state(tmp_path, pristine, "syntax", calc="def add(a, b:\n")
    r = _te(_spec(pristine, hidden)).evaluate(broken)
    assert not r.evaluator_error and r.acceptance is Acceptance.FAIL and r.regression is Regression.FAIL


def test_p_structural_check_feeds_acceptance_and_is_reported_separately(tmp_path):
    pristine, hidden = _task(tmp_path)
    struct = CheckSpec("helper-module-exists", (PY, "-c",
                       "import os, sys; sys.exit(0 if os.path.exists('mathops.py') else 1)"), 30)
    cand = _state(tmp_path, pristine, "c", calc=GOOD)
    r = _te(_spec(pristine, hidden, structural=(struct,))).evaluate(cand)
    assert r.acceptance is Acceptance.FAIL                       # behavior passes, structure fails
    kinds = {c["name"]: (c["kind"], c["status"]) for c in r.checks}
    assert kinds["hidden-accept"] == ("acceptance", "pass")
    assert kinds["helper-module-exists"] == ("structural", "fail")


def test_hanging_check_is_a_task_failure_with_timeout(tmp_path):
    pristine, hidden = _task(tmp_path)
    hang = CheckSpec("hang", (PY, "-c", "import time; time.sleep(30)"), 1.0)
    r = _te(_spec(pristine, hidden, acceptance=(hang,))).evaluate(
        _state(tmp_path, pristine, "c", calc=GOOD))
    c = next(c for c in r.checks if c["name"] == "hang")
    assert c["status"] == "fail" and c["timed_out"] is True and not r.evaluator_error


def test_spec_requires_both_axes_and_relative_paths(tmp_path):
    pristine, hidden = _task(tmp_path)
    with pytest.raises(ValueError):
        _spec(pristine, hidden, regression=())
    with pytest.raises(ValueError):
        _spec(pristine, hidden, protected_paths=("../escape",))


def test_q_hidden_canary_never_reaches_agent_visible_state_or_agent_artifacts(tmp_path):
    pristine, hidden = _task(tmp_path)
    during = {}

    class Agent:
        def run(self, working_copy, envelope, session, *, prompt=None, deadline=None):
            wc = working_copy.path
            text = "".join(p.read_text(errors="replace") for p in wc.rglob("*") if p.is_file())
            during["canary_visible"] = CANARY in text
            during["hidden_dir"] = (wc / "_hidden_tests").exists()
            (wc / "calc.py").write_text(GOOD)
            sid = session.session_id
            return AgentRunOutcome(exit_code=0, session_id=sid, agent_outcome=AgentOutcome.COMPLETED,
                                   stdout="agent says hi", events=[
                                       {"type": "system", "subtype": "init", "session_id": sid},
                                       {"type": "result", "session_id": sid}])

    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs", results_root=tmp_path / "results",
                        home=home)
    m = make_treated_manifest("C1")
    result = life.execute(manifest=m, envelope=implementation_envelope("C1"),
                          session=SessionSpec("new", "99999999-8888-7777-6666-555555555555"),
                          evaluator=_te(_spec(pristine, hidden)), agent_runner=Agent(),
                          cleanup_runner=DryCleanupRunner(), treatment=make_treatment("C1"),
                          task_statement=TEST_STATEMENT)
    assert result.run_validity is RunValidity.VALID
    assert (result.acceptance, result.regression) == (Acceptance.PASS, Regression.PASS)
    assert during == {"canary_visible": False, "hidden_dir": False}
    wc = next((tmp_path / "runs").iterdir())
    for p in wc.rglob("*"):
        if p.is_file():
            assert CANARY.encode() not in p.read_bytes(), p          # incl. every .git object
    run_dir = tmp_path / "results" / m.run_id
    for p in run_dir.iterdir():
        assert CANARY not in p.read_text(encoding="utf-8", errors="replace"), p.name
    ev = json.loads((run_dir / "evaluator.json").read_text())
    assert ev["injected"] == ["check_accept.py", "check_regress.py"]


# --- G5s: fail closed (offline; the real srt sandbox is in test_evaluator_sandbox.py) ---------

def _marker_check(marker):
    code = f"open({str(marker)!r}, 'w').write('ran')"
    return CheckSpec("marker", (PY, "-c", code), 30)


@pytest.mark.parametrize("sandbox", [None, "prepare", "preflight"])
def test_g5s_m_n_no_or_broken_sandbox_is_evaluator_error_and_nothing_runs(tmp_path, sandbox):
    pristine, hidden = _task(tmp_path)
    cand = _state(tmp_path, pristine, "c", calc=GOOD)
    marker = tmp_path / "RAN_UNSANDBOXED"
    spec = _spec(pristine, hidden, acceptance=(_marker_check(marker),))
    fake = {None: None, "prepare": FakeSandbox(fail_prepare="srt cannot initialize"),
            "preflight": FakeSandbox(fail_preflight=True)}[sandbox]
    r = TaskEvaluator(spec, sandbox=fake).evaluate(cand)
    assert r.evaluator_error
    assert (r.acceptance, r.regression) == (Acceptance.ERROR, Regression.ERROR)
    assert all(c["status"] == "error" and c["exit_code"] is None for c in r.checks)
    assert not marker.exists()                                  # never executed, never retried
    if fake is not None:
        assert not any(str(marker) in " ".join(a) for a in fake.wrapped)   # check never wrapped
        assert fake.flights <= 1                                  # no second attempt
    reason = r.checks[0]["reason"]
    assert {None: "no evaluator sandbox", "prepare": "initialization failed",
            "preflight": "preflight failed"}[sandbox] in reason
    assert evaluate_candidate(spec, cand).evaluator_error          # default: no sandbox -> error


def test_g5s_postflight_failure_voids_the_verdict(tmp_path):
    pristine, hidden = _task(tmp_path)
    r = TaskEvaluator(_spec(pristine, hidden), sandbox=FakeSandbox(fail_postflight=True)).evaluate(
        _state(tmp_path, pristine, "c", calc=GOOD))
    assert r.evaluator_error and "post-flight" in r.detail
    assert (r.acceptance, r.regression) == (Acceptance.ERROR, Regression.ERROR)


def test_g5s_sandbox_record_is_in_evaluator_json(tmp_path):
    pristine, hidden = _task(tmp_path)
    r = _te(_spec(pristine, hidden)).evaluate(_state(tmp_path, pristine, "c", calc=GOOD))
    assert r.to_dict()["sandbox"] == {"kind": "test-fake", "production_safe": False}
