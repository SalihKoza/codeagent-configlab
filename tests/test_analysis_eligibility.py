"""G3: analysis eligibility (countability) is separate from run validity (model-free).

Written as ``unittest`` so it also runs under WSL's stdlib-only Python:

    PYTHONPATH=src:tests python3 -m unittest tests.test_analysis_eligibility -v
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codeagent_configlab.lifecycle import AgentRunOutcome, DryCleanupRunner, RunLifecycle  # noqa: E402
from codeagent_configlab.evaluator import SmokeEvaluator  # noqa: E402
from codeagent_configlab.process_control import EXITED  # noqa: E402
from codeagent_configlab.result import RunResult, validate_result_record  # noqa: E402
from codeagent_configlab.session import SessionSpec  # noqa: E402
from codeagent_configlab.status import (  # noqa: E402
    AgentOutcome as AO, AnalysisEligibility as AE, RunValidity as RV,
    check_status_consistency, derive_analysis_eligibility)

COUNT, EXT, INV = AE.COUNTABLE.value, AE.NOT_COUNTABLE_EXTERNAL_INTERRUPTION.value, AE.NOT_COUNTABLE_INVALID.value
SID = "12345678-1234-4234-8234-123456789abc"


class ScriptedAgent:
    def __init__(self, outcome=AO.COMPLETED, exit_code=0, mutate=None, detail=""):
        self.outcome, self.exit_code, self.mutate, self.detail = outcome, exit_code, mutate, detail

    def run(self, working_copy, envelope, session, *, prompt=None, deadline=None):
        if self.mutate:
            self.mutate(working_copy.path)
        sid = session.session_id
        return AgentRunOutcome(exit_code=self.exit_code, session_id=sid, agent_outcome=self.outcome,
                               stdout="", detail=self.detail,
                               events=[{"type": "system", "subtype": "init", "session_id": sid},
                                       {"type": "result", "subtype": "success", "session_id": sid,
                                        "is_error": False}])


def _write(p, text):
    p.write_text(text, encoding="utf-8")


def add_multiply(wc):
    _write(wc / "calc.py", "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n")


def break_add(wc):
    _write(wc / "calc.py", "def multiply(a, b):\n    return a * b\n")


class LifecycleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g3-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_c0(self, agent):
        from _helpers import TEST_STATEMENT, make_treated_manifest
        from codeagent_configlab.envelope import implementation_envelope

        home = self.tmp / "home"
        (home / ".claude" / "projects").mkdir(parents=True, exist_ok=True)
        pristine = self.tmp / "pristine"
        pristine.mkdir(exist_ok=True)
        _write(pristine / "calc.py", "def add(a, b):\n    return a + b\n")
        life = RunLifecycle(pristine=pristine, runs_root=self.tmp / "runs",
                            results_root=self.tmp / "results", home=home)
        m = make_treated_manifest("C0")
        result = life.execute(manifest=m, envelope=implementation_envelope("C0"),
                              session=SessionSpec("new", SID), evaluator=SmokeEvaluator(),
                              agent_runner=agent, cleanup_runner=DryCleanupRunner(), treatment=None,
                              task_statement=TEST_STATEMENT)
        run_dir = self.tmp / "results" / m.run_id
        stored = json.loads((run_dir / "result.json").read_text())
        self.assertEqual(validate_result_record(stored), [])        # schema + invariant
        self.assertEqual(result.validate(), [])
        return result, stored, m, run_dir

    # A-E: legitimate experimental outcomes are countable -----------------------------------
    def test_a_to_e_legitimate_outcomes_are_countable(self):
        cases = {
            "A completed/resolved": (ScriptedAgent(mutate=add_multiply), ("pass", "pass"), "completed"),
            "B acceptance fail": (ScriptedAgent(), ("fail", "pass"), "completed"),
            "C regression fail": (ScriptedAgent(mutate=break_add), ("pass", "fail"), "completed"),
            "D error_exit": (ScriptedAgent(AO.ERROR_EXIT, 1), None, "error_exit"),
            "E timeout": (ScriptedAgent(AO.TIMEOUT, None, detail="timeout:cap_reached"), None, "timeout"),
        }
        for name, (agent, verdicts, outcome) in cases.items():
            with self.subTest(name):
                self.tearDown(); self.setUp()
                result, stored, _, _ = self.run_c0(agent)
                self.assertEqual(stored["run_validity"], "valid")
                self.assertEqual(stored["agent_outcome"], outcome)
                self.assertEqual(stored["analysis_eligibility"],
                                 {"status": COUNT, "reason": f"valid_outcome:{outcome}"})
                if verdicts:
                    self.assertEqual((stored["acceptance"], stored["regression"]), verdicts)

    # F: subscription limit = external interruption, not failure, not invalid ------------------
    def test_f_limit_is_external_non_countable_interruption(self):
        agent = ScriptedAgent(AO.LIMIT_INTERRUPTED, 1, mutate=add_multiply,
                              detail="limit:rate_limit_event_rejected+error=rate_limit")
        result, stored, m, run_dir = self.run_c0(agent)
        self.assertEqual(stored["run_validity"], "valid")
        self.assertIsNone(stored["invalid_reason"])
        self.assertTrue(stored["limit_interrupted"])
        self.assertIn("subscription limit interruption", stored["interruption_reason"])
        self.assertEqual((stored["acceptance"], stored["regression"]), ("not_run", "not_run"))
        self.assertEqual(stored["analysis_eligibility"], {"status": EXT, "reason": "subscription_limit"})
        # planned-cell identity preserved (never deleted): manifest + result on disk, same run id
        manifest = json.loads((run_dir / "manifest.json").read_text())
        self.assertEqual((manifest["run_id"], stored["run_id"]), (m.run_id, m.run_id))
        for key in ("task_id", "configuration", "repetition", "task_version_hash",
                    "settings_policy_hash", "security_policy_hash"):
            self.assertEqual(manifest[key], m.to_dict()[key])

    def test_g_auth_is_non_countable_invalid_infrastructure(self):
        result, stored, _, _ = self.run_c0(ScriptedAgent(AO.AUTH_FAILURE, 1,
                                                         detail="auth:result_api_error_status=401"))
        self.assertEqual(stored["run_validity"], "invalid:infrastructure")
        self.assertEqual(stored["analysis_eligibility"],
                         {"status": INV, "reason": "invalid:infrastructure/auth_failure"})

    def test_h_harness_error_is_non_countable_invalid(self):
        result, stored, _, _ = self.run_c0(ScriptedAgent(AO.HARNESS_ERROR, None, detail="boom"))
        self.assertEqual(stored["run_validity"], "invalid:harness")
        self.assertEqual(stored["analysis_eligibility"]["status"], INV)

    def test_l_informational_rate_limit_run_is_countable(self):
        from test_outcome_classifier import load
        from codeagent_configlab.outcome_classifier import classify_invocation

        c = classify_invocation(0, load("real_success_rate_limit_allowed"))
        self.assertIs(c.outcome, AO.COMPLETED)
        self.assertEqual(derive_analysis_eligibility(RV.VALID, c.outcome, **VERDICT_OK)[0], AE.COUNTABLE)

    def test_m_unclassified_api_error_is_not_turned_into_a_limit(self):
        from test_outcome_classifier import api_error_msg, err_result, init
        from codeagent_configlab.outcome_classifier import classify_invocation

        c = classify_invocation(1, [init(), api_error_msg("rate_limit"), err_result(429)])
        self.assertIs(c.outcome, AO.ERROR_EXIT)                     # observed as-is (G4)
        status, reason = derive_analysis_eligibility(RV.VALID, c.outcome, **VERDICT_OK)
        self.assertEqual((status, reason), (AE.COUNTABLE, "valid_outcome:error_exit"))


class C2Limit(unittest.TestCase):
    """J/K: through RealAgentRunner + a sequenced fake spawn (no claude, no srt)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g3-c2-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _stored(self, result):
        run_dir = next((self.tmp / "results").iterdir())
        stored = json.loads((run_dir / "result.json").read_text())
        self.assertEqual(validate_result_record(stored), [])
        return stored, run_dir

    def test_j_phase1_limit_non_countable_no_phase2(self):
        from test_outcome_classifier import _c2_run, load

        result, spawn, proc = _c2_run(self.tmp, (load("synthetic_limit_rejected"), 1, EXITED, False))
        stored, run_dir = self._stored(result)
        self.assertEqual(len(spawn.calls), 1)
        self.assertEqual(stored["analysis_eligibility"], {"status": EXT, "reason": "subscription_limit"})
        self.assertEqual(stored["run_validity"], "valid")
        self.assertIsNone(stored["phase2_exit_code"])
        self.assertFalse(any(p.name.startswith("phase2.") for p in run_dir.iterdir()))
        self.assertEqual(proc("phase1")["classification"]["outcome"], "limit_interrupted")
        c2 = json.loads((run_dir / "c2.json").read_text())
        self.assertEqual(len(c2["phases"]), 1)

    def test_k_phase2_limit_non_countable_phase1_evidence_kept(self):
        from test_outcome_classifier import _c2_run, load, ok

        result, spawn, proc = _c2_run(self.tmp, ok(), (load("synthetic_limit_rejected"), 1, EXITED, False))
        stored, run_dir = self._stored(result)
        self.assertEqual(len(spawn.calls), 2)
        self.assertEqual(stored["analysis_eligibility"]["status"], EXT)
        self.assertEqual(stored["phase1_exit_code"], 0)
        self.assertEqual(proc("phase1")["classification"]["outcome"], "completed")
        self.assertTrue((run_dir / "phase1.events.jsonl").exists())
        self.assertEqual(proc("phase2")["classification"]["outcome"], "limit_interrupted")
        self.assertEqual((stored["acceptance"], stored["regression"]), ("not_run", "not_run"))


VERDICT_OK = dict(acceptance="fail", regression="pass", evaluator_error=False)
NOT_RUN = dict(acceptance="not_run", regression="not_run", evaluator_error=False)


def _record(**over):
    from codeagent_configlab.status import Acceptance, Regression

    r = RunResult(run_id="r", agent_outcome=AO.COMPLETED, run_validity=RV.VALID,
                  acceptance=Acceptance.PASS, regression=Regression.PASS)
    r.artifacts.evaluator = "evaluator.json"
    r = r.to_dict()
    r.update(over)
    return r


class DerivationAndInvariant(unittest.TestCase):
    def test_derivation_table(self):
        for outcome in ("completed", "error_exit", "timeout"):
            self.assertEqual(derive_analysis_eligibility("valid", outcome, **VERDICT_OK),
                             (AE.COUNTABLE, f"valid_outcome:{outcome}"))
        self.assertEqual(derive_analysis_eligibility("valid", "limit_interrupted", **NOT_RUN),
                         (AE.NOT_COUNTABLE_EXTERNAL_INTERRUPTION, "subscription_limit"))
        # I: every invalidity is non-countable, whatever the outcome (an invalidity outranks a limit)
        for validity in RV:
            if validity is RV.VALID:
                continue
            for outcome in AO:
                self.assertIs(derive_analysis_eligibility(validity, outcome, **VERDICT_OK)[0],
                              AE.NOT_COUNTABLE_INVALID)
        # the timeout / limit distinction is the point of G3
        self.assertNotEqual(derive_analysis_eligibility("valid", "timeout", **VERDICT_OK)[0],
                            derive_analysis_eligibility("valid", "limit_interrupted", **NOT_RUN)[0])

    def test_n_contradictions_rejected(self):
        bad = {
            "limit + countable": _record(agent_outcome="limit_interrupted", limit_interrupted=True,
                                         acceptance="not_run", regression="not_run",
                                         analysis_eligibility={"status": COUNT, "reason": "valid_outcome:limit_interrupted"}),
            "invalid:harness + countable": _record(run_validity="invalid:harness", harness_failure=True,
                                                   agent_outcome="harness_error",
                                                   analysis_eligibility={"status": COUNT, "reason": "x"}),
            "timeout + external interruption": _record(agent_outcome="timeout",
                                                       analysis_eligibility={"status": EXT, "reason": "subscription_limit"}),
            "completed valid + non-countable": _record(analysis_eligibility={"status": INV, "reason": "?"}),
            "limit as invalid:infrastructure": _record(agent_outcome="limit_interrupted", limit_interrupted=True,
                                                       acceptance="not_run", regression="not_run",
                                                       run_validity="invalid:infrastructure",
                                                       analysis_eligibility=None),
            "limit with a verdict": _record(agent_outcome="limit_interrupted", limit_interrupted=True,
                                            acceptance="pass", regression="pass", analysis_eligibility=None),
            "limit flag without outcome": _record(limit_interrupted=True),
            "auth flag mismatch": _record(auth_failure=True),
            "auth recorded valid": _record(agent_outcome="auth_failure", auth_failure=True, analysis_eligibility=None),
            "harness recorded valid": _record(agent_outcome="harness_error", analysis_eligibility=None),
        }
        for name, rec in bad.items():
            with self.subTest(name):
                self.assertTrue(check_status_consistency(rec), name)

    def test_o_schema_round_trip_and_pre_g3_records(self):
        rec = json.loads(json.dumps(_record()))
        self.assertEqual(validate_result_record(rec), [])
        self.assertEqual(rec["analysis_eligibility"], {"status": COUNT, "reason": "valid_outcome:completed"})
        old = dict(rec)
        del old["analysis_eligibility"]                       # a record written before G3
        self.assertEqual(validate_result_record(old), [])
        rec["analysis_eligibility"] = {"status": "maybe", "reason": "x"}
        self.assertTrue(validate_result_record(rec))         # enum enforced by the schema

    def test_default_result_object_is_never_countable(self):
        # RunResult() defaults to harness_error + valid: contradictory, so never counted, and flagged
        d = RunResult(run_id="x").to_dict()
        self.assertEqual(d["analysis_eligibility"]["status"], INV)
        self.assertTrue(check_status_consistency(d))


if __name__ == "__main__":
    unittest.main()
