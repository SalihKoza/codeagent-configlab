"""G8: evaluator-infrastructure error vs agent-caused failure (model-free).

Written as ``unittest`` so it also runs under WSL's stdlib-only Python:

    PYTHONPATH=src:tests python3 -m unittest tests.test_g8_evaluator_errors -v

Evaluator-level cases use the offline ``FakeSandbox`` (identity wrapper + Python launcher); the
real srt launcher is exercised in ``test_evaluator_sandbox.py`` on WSL.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from _helpers import FakeSandbox  # noqa: E402

from codeagent_configlab.evaluator import EvaluationResult, SmokeEvaluator  # noqa: E402
from codeagent_configlab.result import validate_result_record  # noqa: E402
from codeagent_configlab.status import (  # noqa: E402
    Acceptance, AnalysisEligibility as AE, Regression, check_status_consistency)
from codeagent_configlab.task_evaluator import (  # noqa: E402
    CheckSpec, TaskEvaluator, TaskEvaluatorSpec, overlay_candidate, split_exit_trailer)

PY = sys.executable
PENDING = AE.NOT_COUNTABLE_EVALUATION_PENDING.value


def _chk(name, code, timeout=30):
    return CheckSpec(name, (PY, "-c", code), timeout)


OK = _chk("ok", "print('hello')")
FAIL1 = _chk("fails", "raise SystemExit(1)")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g8-"))
        self.pristine = self.tmp / "pristine"
        self.pristine.mkdir()
        (self.pristine / "app.py").write_text("x = 1\n")
        self.hidden = self.tmp / "hidden"
        self.hidden.mkdir()
        (self.hidden / "h.py").write_text("pass\n")
        self.cand = overlay_candidate(self.pristine, None, self.tmp / "cand")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def spec(self, acceptance=(OK,), regression=(OK,), structural=(), **kw):
        base = dict(pristine=self.pristine, hidden_dir=self.hidden, acceptance=acceptance,
                    regression=regression, structural=structural)
        base.update(kw)
        return TaskEvaluatorSpec(**base)

    def ev(self, sandbox=None, candidate=None, **spec_kw):
        return TaskEvaluator(self.spec(**spec_kw), sandbox=sandbox or FakeSandbox()).evaluate(
            candidate or self.cand)

    def check(self, res, name):
        return next(c for c in res.checks if c["name"] == name)


class TaskFailuresStayTaskFailures(Base):
    def test_a_b_c_nonzero_checks_are_fail_not_error(self):
        for axis in ("acceptance", "regression", "structural"):
            with self.subTest(axis):
                kw = {axis: (FAIL1,)}
                r = self.ev(**kw)
                self.assertFalse(r.evaluator_error, r.detail)
                self.assertEqual(self.check(r, "fails")["status"], "fail")
                if axis == "regression":
                    self.assertIs(r.regression, Regression.FAIL)
                else:
                    self.assertIs(r.acceptance, Acceptance.FAIL)

    def test_check_timeout_stays_fail(self):
        r = self.ev(acceptance=(_chk("hang", "import time; time.sleep(30)", 1.0),))
        c = self.check(r, "hang")
        self.assertEqual((c["status"], c["timed_out"]), ("fail", True))
        self.assertFalse(r.evaluator_error)

    def test_trailer_is_stripped_from_output(self):
        r = self.ev()
        tail = self.check(r, "ok")["stdout_tail"]
        self.assertIn("hello", tail)
        self.assertNotIn("CCLAB-EVAL-RC", tail)


class InfrastructureErrors(Base):
    def test_e_mid_run_sandbox_failure_is_error_not_fail(self):
        marker = self.tmp / "RAN"
        run_it = _chk("mid-run", f"open({str(marker)!r}, 'w').write('x'); raise SystemExit(1)  # MIDRUN")
        sb = FakeSandbox(launcher_fails_for={"MIDRUN"})
        r = self.ev(sandbox=sb, acceptance=(run_it,))
        c = self.check(r, "mid-run")
        self.assertEqual(c["status"], "error")
        self.assertIn("did not attest", c["reason"])
        self.assertTrue(r.evaluator_error)
        self.assertIs(r.acceptance, Acceptance.ERROR)
        self.assertIs(r.regression, Regression.PASS)          # other axis unaffected
        self.assertFalse(marker.exists())                     # never run outside the launcher
        self.assertEqual(sb.check_runs, 2)                    # one attempt per check, no retry

    def test_e_forged_or_mismatched_attestation_is_error(self):
        forged = _chk("forged", "raise SystemExit(3)  # FORGE")
        r = self.ev(sandbox=FakeSandbox(forge_trailer_for={"FORGE"}), acceptance=(forged,))
        self.assertEqual(self.check(r, "forged")["status"], "error")
        self.assertTrue(r.evaluator_error)

    def test_trailer_parser_only_trusts_the_last_line(self):
        self.assertEqual(split_exit_trailer(b"out\n\nCCLAB-EVAL-RC:n1:4\n", "n1"), (4, b"out\n"))
        self.assertEqual(split_exit_trailer(b"CCLAB-EVAL-RC:n1:0\nmore\n", "n1")[0], None)
        self.assertEqual(split_exit_trailer(b"CCLAB-EVAL-RC:other:0\n", "n1")[0], None)
        self.assertEqual(split_exit_trailer(b"", "n1")[0], None)

    def test_d_startup_and_preflight_failures(self):
        for sb in (FakeSandbox(fail_prepare="srt cannot initialize"), FakeSandbox(fail_preflight=True)):
            r = self.ev(sandbox=sb)
            self.assertTrue(r.evaluator_error)
            self.assertEqual((r.acceptance, r.regression), (Acceptance.ERROR, Regression.ERROR))

    def test_g_missing_trusted_sources(self):
        r = self.ev(hidden_dir=self.tmp / "no-hidden")
        self.assertTrue(r.evaluator_error and "hidden" in r.detail)
        shutil.rmtree(self.pristine)
        r = self.ev(protected_paths=("tests/test_x.py",))
        self.assertTrue(r.evaluator_error)
        self.assertIn("pristine", r.detail)

    def test_h_evaluator_copy_failure(self):
        r = self.ev(candidate=self.tmp / "does-not-exist")
        self.assertTrue(r.evaluator_error)
        self.assertIn("setup failed", r.detail)


# --- lifecycle level ----------------------------------------------------------------------

class FixedEvaluator:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, 0

    def evaluate(self, wc):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result


def infra_error():
    return EvaluationResult(Acceptance.ERROR, Regression.ERROR, evaluator_error=True,
                            detail="evaluator sandbox preflight failed: simulated")


def fail_with_output(text, key_text=None):
    check = {"kind": "acceptance", "name": "t", "status": "fail", "reason": "exit code 1",
             "exit_code": 1, "timed_out": False, "stdout_tail": text, "stderr_tail": ""}
    if key_text:
        check[key_text] = "x"
    return EvaluationResult(Acceptance.FAIL, Regression.PASS, checks=[check], detail="ok")


def run_life(tmp, config, evaluator):
    from _helpers import TEST_STATEMENT, make_treated_manifest, make_treatment
    from test_outcome_classifier import SequencedSpawn, ok

    from codeagent_configlab.envelope import implementation_envelope
    from codeagent_configlab.lifecycle import DryCleanupRunner, RunLifecycle
    from codeagent_configlab.runners import RealAgentRunner
    from codeagent_configlab.session import SessionSpec

    home = tmp / "home"
    (home / ".claude" / "projects").mkdir(parents=True, exist_ok=True)
    pristine = tmp / "pristine-life"
    pristine.mkdir(exist_ok=True)
    (pristine / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    spawn = SequencedSpawn(ok(), ok())
    runner = RealAgentRunner(home=str(home), harness_root=str(tmp / "hr"), model="m", effort="high",
                             prompt="p", tmp_root=str(tmp / "tmp"), spawn=spawn, srt_path="/s",
                             claude_path="/c")
    life = RunLifecycle(pristine=pristine, runs_root=tmp / f"runs-{config}",
                        results_root=tmp / "results", home=home)
    m = make_treated_manifest(config)
    life.execute(manifest=m, envelope=implementation_envelope(config),
                 session=SessionSpec("new", "12345678-1234-4234-8234-12345678%04d" % len(config)),
                 evaluator=evaluator, agent_runner=runner, cleanup_runner=DryCleanupRunner(),
                 treatment=make_treatment(config), task_statement=TEST_STATEMENT)
    run_dir = tmp / "results" / m.run_id
    stored = json.loads((run_dir / "result.json").read_text())
    return stored, run_dir, spawn


class LifecycleSemantics(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g8-life-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def assertAuditable(self, stored, run_dir):
        self.assertEqual(validate_result_record(stored), [])
        self.assertTrue((run_dir / "evaluator.json").exists())
        self.assertEqual(stored["artifacts"]["evaluator"], "evaluator.json")

    def test_i_j_evaluator_error_keeps_validity_and_is_pending(self):
        stored, run_dir, _ = run_life(self.tmp, "C0", FixedEvaluator(infra_error()))
        self.assertAuditable(stored, run_dir)
        self.assertEqual((stored["agent_outcome"], stored["run_validity"]), ("completed", "valid"))
        self.assertTrue(stored["evaluator_error"])
        self.assertEqual(stored["analysis_eligibility"], {"status": PENDING, "reason": "evaluator_error"})

    def test_k_valid_acceptance_fail_is_countable(self):
        stored, run_dir, _ = run_life(self.tmp, "C0", SmokeEvaluator())
        self.assertAuditable(stored, run_dir)
        self.assertEqual((stored["acceptance"], stored["evaluator_error"]), ("fail", False))
        self.assertEqual(stored["analysis_eligibility"]["status"], AE.COUNTABLE.value)

    def test_l_same_semantics_for_c0_c1_c2(self):
        seen = {}
        for config in ("C0", "C1", "C2"):
            stored, run_dir, spawn = run_life(self.tmp, config, FixedEvaluator(infra_error()))
            self.assertAuditable(stored, run_dir)
            seen[config] = (stored["run_validity"], stored["evaluator_error"],
                            stored["acceptance"], stored["regression"],
                            json.dumps(stored["analysis_eligibility"]))
            if config == "C2":
                self.assertEqual(len(spawn.calls), 2)
                for name in ("phase1.process.json", "phase2.process.json", "c2.json"):
                    self.assertTrue((run_dir / name).exists(), name)
        self.assertEqual(len(set(seen.values())), 1, seen)

    def test_m_o_raising_evaluator_is_auditable_and_not_retried(self):
        evaluator = FixedEvaluator(exc=RuntimeError("sandbox runtime vanished"))
        stored, run_dir, _ = run_life(self.tmp, "C0", evaluator)
        self.assertAuditable(stored, run_dir)
        self.assertEqual(evaluator.calls, 1)
        ev = json.loads((run_dir / "evaluator.json").read_text())
        self.assertTrue(ev["evaluator_error"])
        self.assertIn("RuntimeError", ev["detail"])
        self.assertEqual(stored["analysis_eligibility"]["status"], PENDING)

    def test_n_secret_marker_in_output_is_withheld_verdict_kept(self):
        marker = ".credentials.json"
        stored, run_dir, _ = run_life(self.tmp, "C0",
                                      FixedEvaluator(fail_with_output(f"cat ~/.claude/{marker}")))
        self.assertAuditable(stored, run_dir)
        ev = json.loads((run_dir / "evaluator.json").read_text())
        self.assertTrue(ev["output_withheld"])
        self.assertTrue(ev["checks"][0]["stdout_tail"].startswith("[withheld: secret-scan marker"))
        self.assertEqual((stored["acceptance"], stored["evaluator_error"]), ("fail", False))
        self.assertEqual(stored["analysis_eligibility"]["status"], AE.COUNTABLE.value)
        for p in run_dir.iterdir():
            self.assertNotIn(marker, p.read_text(encoding="utf-8", errors="replace"), p.name)

    def test_n_unfinalizable_record_becomes_evaluator_error(self):
        # a marker the placeholder pass cannot remove (it sits in a key) -> metadata-only record
        stored, run_dir, _ = run_life(self.tmp, "C0",
                                      FixedEvaluator(fail_with_output("x", key_text=".credentials.json")))
        self.assertAuditable(stored, run_dir)
        ev = json.loads((run_dir / "evaluator.json").read_text())
        self.assertTrue(ev["finalization_failed"])
        self.assertTrue(stored["evaluator_error"])
        self.assertEqual(stored["analysis_eligibility"]["status"], PENDING)


class Invariants(unittest.TestCase):
    def _rec(self, **over):
        from codeagent_configlab.result import RunResult
        from codeagent_configlab.status import AgentOutcome, RunValidity

        r = RunResult(run_id="r", agent_outcome=AgentOutcome.COMPLETED, run_validity=RunValidity.VALID,
                      acceptance=Acceptance.PASS, regression=Regression.PASS)
        r.artifacts.evaluator = "evaluator.json"
        d = r.to_dict()
        d.update(over)
        return d

    def test_contradictions_rejected(self):
        bad = {
            "evaluator error + countable": self._rec(acceptance="error", evaluator_error=True,
                                                     analysis_eligibility={"status": "countable", "reason": "x"}),
            "error verdict without flag": self._rec(acceptance="error", analysis_eligibility=None),
            "flag without error verdict": self._rec(evaluator_error=True, analysis_eligibility=None),
            "verdict without evaluator record": self._rec(artifacts={**self._rec()["artifacts"], "evaluator": None}),
            "missing verdict + countable": self._rec(acceptance="not_run", regression="not_run",
                                                     analysis_eligibility={"status": "countable",
                                                                           "reason": "valid_outcome:completed"}),
        }
        for name, rec in bad.items():
            with self.subTest(name):
                self.assertTrue(check_status_consistency(rec))

    def test_ordinary_fail_is_countable_and_consistent(self):
        rec = self._rec(acceptance="fail", analysis_eligibility=None)
        rec.pop("analysis_eligibility")
        self.assertEqual(check_status_consistency(rec), [])


if __name__ == "__main__":
    unittest.main()
