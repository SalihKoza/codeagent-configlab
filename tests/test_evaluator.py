"""Smoke evaluator: runs on a copy, distinguishes evaluator error from task failure."""

from pathlib import Path

from codeagent_configlab.evaluator import SmokeEvaluator
from codeagent_configlab.status import Acceptance, Regression


def _wc(tmp_path: Path, body: str) -> Path:
    wc = tmp_path / "wc"
    wc.mkdir()
    (wc / "calc.py").write_text(body, encoding="utf-8")
    return wc


def test_acceptance_pass_when_feature_present(tmp_path):
    wc = _wc(tmp_path, "def add(a,b):\n return a+b\n\ndef multiply(a,b):\n return a*b\n")
    r = SmokeEvaluator().evaluate(wc)
    assert r.acceptance is Acceptance.PASS and r.regression is Regression.PASS
    assert not r.evaluator_error


def test_task_failure_when_feature_absent(tmp_path):
    wc = _wc(tmp_path, "def add(a,b):\n return a+b\n")
    r = SmokeEvaluator().evaluate(wc)
    assert r.acceptance is Acceptance.FAIL      # task failed, but this is NOT an evaluator error
    assert r.regression is Regression.PASS
    assert not r.evaluator_error


def test_regression_fail_when_baseline_broken(tmp_path):
    wc = _wc(tmp_path, "def multiply(a,b):\n return a*b\n")  # add() removed
    r = SmokeEvaluator().evaluate(wc)
    assert r.regression is Regression.FAIL


def test_evaluator_error_when_target_missing(tmp_path):
    wc = tmp_path / "wc"
    wc.mkdir()
    r = SmokeEvaluator().evaluate(wc)
    assert r.evaluator_error is True
    assert r.acceptance is Acceptance.ERROR


def test_evaluation_does_not_mutate_final_working_copy(tmp_path):
    body = "def add(a,b):\n return a+b\n\ndef multiply(a,b):\n return a*b\n"
    wc = _wc(tmp_path, body)
    SmokeEvaluator().evaluate(wc)
    # the evaluator works on a copy; the given WC is unchanged and still the only calc.py
    assert (wc / "calc.py").read_text() == body
    assert list(p.name for p in wc.iterdir()) == ["calc.py"]
