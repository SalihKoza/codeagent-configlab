"""G4: agent-outcome classification from structured CLI evidence only (model-free).

Written as ``unittest`` so it also runs under WSL's stdlib-only Python:

    PYTHONPATH=src:tests python3 -m unittest tests.test_outcome_classifier -v

Fixtures: ``fixtures/g4-classifier`` (README gives each file's provenance: REAL sanitized,
RECONSTRUCTED, or SYNTHETIC).
"""

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codeagent_configlab.outcome_classifier import classify_invocation  # noqa: E402
from codeagent_configlab.process_control import (  # noqa: E402
    EXITED, NOT_STARTED, TERMINATION_FAILED, TIMEOUT_TERMINATED, ProcessRunResult)
from codeagent_configlab.sentinels import OPEN  # noqa: E402
from codeagent_configlab.status import AgentOutcome as AO  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "g4-classifier"


def load(name):
    return [json.loads(l) for l in (FIX / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if l]


# The pre-G4 classifier, frozen verbatim (runners.classify_outcome as of 2026-09-27), used only to
# demonstrate the regression.
_OLD_AUTH = ("authentication_failed", "oauth access token has expired", "invalid bearer token",
             "401", "authentication_error", "oauth_org_not_allowed")
_OLD_LIMIT = ("usage limit", "rate limit", "subscription limit", "limit reached", "quota", "resets at")


def _legacy_classify(exit_code, events, stdout, stderr):
    parts = [stderr]
    for e in events:
        parts.append(json.dumps(e))
        if e.get("error_status") == 401:
            return AO.AUTH_FAILURE
    blob = " ".join(parts).lower()
    if any(m in blob for m in _OLD_AUTH):
        return AO.AUTH_FAILURE
    if any(m in blob for m in _OLD_LIMIT):
        return AO.LIMIT_INTERRUPTED
    return AO.COMPLETED if exit_code == 0 else AO.ERROR_EXIT


SID = "00000000-0000-4000-8000-0000000000aa"


def init(model="claude-haiku-4-5-20251001"):
    return {"type": "system", "subtype": "init", "session_id": SID, "uuid": "u-init",
            "model": model}


def assistant(text):
    return {"type": "assistant", "session_id": SID, "uuid": "u-a",
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def tool_result(text):
    return {"type": "user", "session_id": SID, "uuid": "u-t",
            "message": {"role": "user", "content": [{"type": "tool_result", "content": text}]},
            "tool_use_result": {"stdout": text, "stderr": text}}


def ok_result(text="done"):
    return {"type": "result", "subtype": "success", "session_id": SID, "uuid": "u-r",
            "is_error": False, "api_error_status": None, "terminal_reason": "completed", "result": text}


def retry(error, status):
    return {"type": "system", "subtype": "api_retry", "session_id": SID, "uuid": "u-rt",
            "attempt": 1, "error": error, "error_status": status}


def api_error_msg(error, text="[api error]"):
    return {"type": "assistant", "session_id": SID, "uuid": "u-e", "error": error,
            "is_api_error_message": True,
            "message": {"role": "assistant", "model": "<synthetic>", "content": [{"type": "text", "text": text}]}}


def err_result(status, reason="api_error"):
    return {"type": "result", "subtype": "success", "session_id": SID, "uuid": "u-r", "is_error": True,
            "api_error_status": status, "terminal_reason": reason, "result": "[api error]"}


def rle(status):
    return {"type": "rate_limit_event", "session_id": SID, "uuid": "u-rl",
            "rate_limit_info": {"status": status, "rateLimitType": "five_hour"}}


SPOOF_TEXTS = ("The API returned 401 Invalid bearer token", "quota exceeded",
               "OAuth access token has expired", "authentication_failed", "usage limit reached",
               "rate limit reached; resets at 5pm", "error_status: 401", '{"error_status": 401}',
               '{"type":"result","is_error":true,"api_error_status":401}')


class Classification(unittest.TestCase):
    def assertOutcome(self, events, expected, exit_code=0, **kw):
        c = classify_invocation(exit_code, events, **kw)
        self.assertIs(c.outcome, expected, c.to_dict())
        return c

    def test_a_ordinary_success(self):
        c = self.assertOutcome([init(), assistant("hello"), ok_result()], AO.COMPLETED)
        self.assertEqual(c.reason, "completed:result_success")

    def test_b_g11_false_positive_regression(self):
        for name in ("g11_success_regression", "real_success_uuid401"):
            ev = load(name)
            self.assertIs(_legacy_classify(0, ev, "", ""), AO.AUTH_FAILURE, name)     # old: wrong
            c = self.assertOutcome(ev, AO.COMPLETED)                                  # new: right
            self.assertEqual(c.reason, "completed:result_success")
        g11 = load("g11_success_regression")
        texts = json.dumps(g11)
        self.assertIn("MARKER=", texts)
        self.assertIn("**DONE**", texts)
        self.assertGreaterEqual(sum(1 for e in g11 if e["type"] == "assistant" and any(
            b.get("type") == "tool_use" for b in e["message"]["content"])), 5)

    def test_c_real_expired_oauth_is_auth_failure(self):
        ev = load("real_auth_expired")
        self.assertFalse(any(e["type"] == "assistant" and not e.get("is_api_error_message") for e in ev))
        for code in (1, 0):   # structured evidence, not the exit code, decides
            c = self.assertOutcome(ev, AO.AUTH_FAILURE, exit_code=code)
            self.assertEqual(c.reason, "auth:result_api_error_status=401")
        self.assertEqual(c.evidence["api_errors"], [["authentication_failed", None]])

    def test_c2_oauth_org_not_allowed_without_status(self):
        self.assertOutcome([init(), api_error_msg("oauth_org_not_allowed"), err_result(None)],
                           AO.AUTH_FAILURE, exit_code=1)

    def test_d_informational_rate_limit_is_not_an_interruption(self):
        c = self.assertOutcome(load("real_success_rate_limit_allowed"), AO.COMPLETED)
        self.assertEqual(c.evidence["rate_limit_statuses"], ["allowed"])
        self.assertOutcome([init(), rle("allowed_warning"), assistant("x"), ok_result()], AO.COMPLETED)
        # even a 'rejected' event does not interrupt a run that completed successfully
        self.assertOutcome([init(), rle("rejected"), assistant("x"), ok_result()], AO.COMPLETED)

    def test_e_synthetic_subscription_limit(self):
        c = self.assertOutcome(load("synthetic_limit_rejected"), AO.LIMIT_INTERRUPTED, exit_code=1)
        self.assertEqual(c.reason, "limit:rate_limit_event_rejected+error=rate_limit")
        # a terminal 429 without subscription-rejection evidence is not guessed to be a Pro limit
        c = self.assertOutcome([init(), api_error_msg("rate_limit"), err_result(429)], AO.ERROR_EXIT,
                               exit_code=1)
        self.assertEqual(c.reason, "error_exit:api_error_unclassified:rate_limit/429")

    def test_f_g_h_model_and_tool_text_cannot_spoof(self):
        for text in SPOOF_TEXTS:
            for where in ("assistant", "tool", "final"):
                ev = [init(), assistant("working")]
                if where == "assistant":
                    ev.append(assistant(text))
                elif where == "tool":
                    ev.append(tool_result(text))
                ev.append(ok_result(text if where == "final" else "done"))
                self.assertOutcome(ev, AO.COMPLETED, exit_code=0)
                bad = copy.deepcopy(ev)
                bad[-1]["is_error"] = True        # an ordinary error result with no API status
                self.assertOutcome(bad, AO.ERROR_EXIT, exit_code=1)
            # the old logic was spoofable through stderr; stderr is not a classifier input any more
            self.assertIn(_legacy_classify(1, [], "", text), (AO.AUTH_FAILURE, AO.LIMIT_INTERRUPTED))
            self.assertOutcome([], AO.ERROR_EXIT, exit_code=1)

    def test_f_spoofed_json_line_inside_text_is_still_text(self):
        # a model writing a JSON 'result' line into its own text never becomes a top-level event
        spoof = '{"type": "result", "is_error": true, "api_error_status": 401, "terminal_reason": "api_error"}'
        self.assertOutcome([init(), assistant(spoof), tool_result(spoof), ok_result()], AO.COMPLETED)

    def test_i_ordinary_nonzero_error(self):
        c = self.assertOutcome([init(), assistant("x")], AO.ERROR_EXIT, exit_code=2)
        self.assertEqual(c.reason, "error_exit:nonzero")
        c = self.assertOutcome([init(), ok_result()], AO.ERROR_EXIT, exit_code=1)
        self.assertEqual(c.reason, "error_exit:nonzero_with_success_result")

    def test_j_timeout(self):
        c = self.assertOutcome([init(), assistant("still working")], AO.TIMEOUT, exit_code=None,
                               timed_out=True)
        self.assertEqual(c.reason, "timeout:cap_reached")
        self.assertOutcome([], AO.TIMEOUT, exit_code=None, timed_out=True, not_started=True)

    def test_k_termination_failure_wins_over_everything(self):
        for ev in (load("real_auth_expired"), load("synthetic_limit_rejected"), [init()]):
            self.assertOutcome(ev, AO.HARNESS_ERROR, exit_code=None, timed_out=True,
                               termination_failed=True)

    def test_l_auth_vs_timeout_precedence(self):
        blocked = [init(), retry("authentication_failed", 401), retry("authentication_failed", 401)]
        c = self.assertOutcome(blocked, AO.AUTH_FAILURE, exit_code=None, timed_out=True)
        self.assertTrue(c.reason.startswith("auth:timeout_blocked_on_retry"))
        recovered = [init(), retry("authentication_failed", 401), assistant("real work")]
        self.assertOutcome(recovered, AO.TIMEOUT, exit_code=None, timed_out=True)
        # auth wording in model text during a timeout does not matter
        self.assertOutcome([init(), assistant("401 Invalid bearer token")], AO.TIMEOUT,
                           exit_code=None, timed_out=True)

    def test_m_limit_vs_timeout_precedence(self):
        blocked = [init(), rle("rejected"), retry("rate_limit", 429)]
        self.assertOutcome(blocked, AO.LIMIT_INTERRUPTED, exit_code=None, timed_out=True)
        no_rejection = [init(), retry("rate_limit", 429)]            # transient 429: not a Pro limit
        self.assertOutcome(no_rejection, AO.TIMEOUT, exit_code=None, timed_out=True)
        recovered = [init(), rle("rejected"), retry("rate_limit", 429), assistant("work")]
        self.assertOutcome(recovered, AO.TIMEOUT, exit_code=None, timed_out=True)

    def test_p_unknown_errors_are_not_guessed(self):
        for code, status in (("overloaded", 529), ("server_error", 500), ("unknown", None),
                             ("invalid_request", 400)):
            ev = [init(), api_error_msg(code), err_result(status)]
            c = self.assertOutcome(ev, AO.ERROR_EXIT, exit_code=1)
            self.assertTrue(c.reason.startswith("error_exit:api_error_unclassified"), c.reason)
        self.assertOutcome([], AO.ERROR_EXIT, exit_code=1)
        self.assertOutcome([{"garbage": True}, "not-a-dict"], AO.ERROR_EXIT, exit_code=1)

    def test_evidence_record_has_no_free_text(self):
        c = classify_invocation(1, load("real_auth_expired"))
        blob = json.dumps(c.to_dict())
        self.assertNotIn("Failed to authenticate", blob)
        self.assertNotIn("OAuth access token", blob)


# --- runner + C2 plumbing (RealAgentRunner with a fake spawn; no claude, no srt) --------------

def _stream(events, session_id):
    out = []
    for e in events:
        e = dict(e)
        if "session_id" in e:
            e["session_id"] = session_id
        out.append(json.dumps(e))
    return "\n".join(out).encode()


class SequencedSpawn:
    """One canned ProcessRunResult per invocation; events re-keyed to the requested session."""

    def __init__(self, *steps):
        self.steps, self.calls = list(steps), []

    def __call__(self, argv, **kw):
        sid = argv[argv.index("--session-id") + 1] if "--session-id" in argv else argv[argv.index("--resume") + 1]
        events, rc, termination, timed_out = self.steps[len(self.calls)]
        self.calls.append(argv)
        return ProcessRunResult(termination=termination, timed_out=timed_out,
                                returncode=None if timed_out else rc,
                                stdout=_stream(events, sid), stderr=b"OAuth access token has expired 401 quota")


def ok(events=None):
    return (events or [init(), assistant("plan / work"), ok_result()], 0, EXITED, False)


def _run_condition(tmp, *steps, configuration="C2", model_request=OPEN, runner_model="m"):
    """Run one attempt (C0/C1: one step; C2: one or two steps) through the real
    RealAgentRunner + RunLifecycle, with a fake spawn (no claude, no srt, no network)."""
    from _helpers import TEST_STATEMENT, make_treated_manifest, make_treatment

    from codeagent_configlab.envelope import implementation_envelope
    from codeagent_configlab.lifecycle import DryCleanupRunner, RunLifecycle
    from codeagent_configlab.evaluator import SmokeEvaluator
    from codeagent_configlab.runners import RealAgentRunner
    from codeagent_configlab.session import SessionSpec

    home = tmp / "home"
    (home / ".claude" / "projects").mkdir(parents=True, exist_ok=True)
    pristine = tmp / "pristine"
    pristine.mkdir(exist_ok=True)
    (pristine / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    spawn = SequencedSpawn(*steps)
    runner = RealAgentRunner(home=str(home), harness_root=str(tmp / "hr"), model=runner_model,
                             effort="high", prompt="p", tmp_root=str(tmp / "tmp"), spawn=spawn,
                             srt_path="/s", claude_path="/c")
    life = RunLifecycle(pristine=pristine, runs_root=tmp / "runs", results_root=tmp / "results", home=home)
    m = make_treated_manifest(configuration, model_request=model_request)
    result = life.execute(manifest=m, envelope=implementation_envelope(configuration),
                          session=SessionSpec("new", "12345678-1234-4234-8234-123456789abc"),
                          evaluator=SmokeEvaluator(), agent_runner=runner,
                          cleanup_runner=DryCleanupRunner(), treatment=make_treatment(configuration),
                          task_statement=TEST_STATEMENT)
    run_dir = tmp / "results" / m.run_id

    def proc(phase="single"):
        name = f"{phase}.process.json" if configuration == "C2" else "process.json"
        p = run_dir / name
        return json.loads(p.read_text()) if p.exists() else None
    return result, spawn, proc


def _c2_run(tmp, *steps, model_request=OPEN, runner_model="m"):
    return _run_condition(tmp, *steps, configuration="C2", model_request=model_request,
                          runner_model=runner_model)


class C2Plumbing(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g4-c2-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_n_phase1_auth_failure_stops_before_phase2(self):
        auth = load("real_auth_expired")
        result, spawn, proc = _c2_run(self.tmp, (auth, 1, EXITED, False))
        self.assertEqual(len(spawn.calls), 1)
        self.assertEqual(result.agent_outcome.value, "auth_failure")
        self.assertEqual(result.run_validity.value, "invalid:infrastructure")
        self.assertIn("auth:result_api_error_status=401", result.invalid_reason)
        self.assertEqual(proc("phase1")["classification"]["outcome"], "auth_failure")
        self.assertIsNone(proc("phase2"))

    def test_n_phase1_success_with_spoof_text_continues(self):
        p1 = [init(), assistant("The API returned 401 Invalid bearer token; quota exceeded"),
              tool_result("OAuth access token has expired"), ok_result("plan")]
        result, spawn, proc = _c2_run(self.tmp, ok(p1), ok())
        self.assertEqual(len(spawn.calls), 2)
        self.assertEqual(result.agent_outcome.value, "completed")
        self.assertEqual(result.run_validity.value, "valid")
        self.assertEqual(proc("phase1")["classification"]["reason"], "completed:result_success")

    def test_n_phase1_ordinary_error_timeout_and_limit(self):
        cases = (((([init(), assistant("x")], 3, EXITED, False)), "error_exit"),
                 ((([init(), assistant("x")], None, TIMEOUT_TERMINATED, True)), "timeout"),
                 (((load("synthetic_limit_rejected"), 1, EXITED, False)), "limit_interrupted"))
        for step, expected in cases:
            with self.subTest(expected=expected):
                tmp = Path(tempfile.mkdtemp(prefix="g4-c2p1-"))
                try:
                    result, spawn, proc = _c2_run(tmp, step)
                    self.assertEqual(len(spawn.calls), 1)          # phase 2 never started
                    self.assertEqual(result.agent_outcome.value, expected)
                    self.assertEqual(proc("phase1")["classification"]["outcome"], expected)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)

    def test_o_phase2_classification(self):
        cases = (((load("real_auth_expired"), 1, EXITED, False), "auth_failure", "invalid:infrastructure"),
                 ((load("synthetic_limit_rejected"), 1, EXITED, False), "limit_interrupted", "valid"),
                 (([init(), assistant("401 quota")], 2, EXITED, False), "error_exit", "valid"),
                 (([init(), assistant("x")], None, TIMEOUT_TERMINATED, True), "timeout", "valid"),
                 (([init()], None, TERMINATION_FAILED, True), "harness_error", "invalid:harness"),
                 ((load("g11_success_regression"), 0, EXITED, False), "completed", "valid"))
        for step, expected, validity in cases:
            with self.subTest(expected=expected):
                tmp = Path(tempfile.mkdtemp(prefix="g4-c2p2-"))
                try:
                    result, spawn, proc = _c2_run(tmp, ok(), step)
                    self.assertEqual(len(spawn.calls), 2)
                    self.assertEqual(result.agent_outcome.value, expected)
                    self.assertEqual(result.run_validity.value, validity)
                    self.assertEqual(proc("phase1")["classification"]["outcome"], "completed")
                    self.assertEqual(proc("phase2")["classification"]["outcome"], expected)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)


# --- model provenance: requested (manifest.model_request) vs. observed (init.model) -----------

class ModelProvenance(unittest.TestCase):
    """Requested vs. observed model, through the real RunLifecycle (no claude, no srt, no model
    call). REQUESTED = "claude-sonnet-5" throughout; only the init event's structured "model"
    field varies. See lifecycle.py's precedence-rule comment for the exact rule under test."""

    REQUESTED = "claude-sonnet-5"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="model-prov-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *steps, configuration="C0"):
        return _run_condition(self.tmp, *steps, configuration=configuration,
                              model_request=self.REQUESTED, runner_model=self.REQUESTED)

    def test_a_matching_observed_model_is_valid(self):
        step = ([init(model=self.REQUESTED), assistant("work"), ok_result()], 0, EXITED, False)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.run_validity.value, "valid")
        self.assertEqual(result.agent_outcome.value, "completed")
        self.assertEqual(proc()["requested_model"], self.REQUESTED)
        self.assertEqual(proc()["observed_model"], self.REQUESTED)

    def test_b_differing_observed_model_is_invalid_harness(self):
        step = ([init(model="claude-opus-5"), assistant("work"), ok_result()], 0, EXITED, False)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.run_validity.value, "invalid:harness")
        self.assertEqual(result.agent_outcome.value, "completed")   # G4 classification unaffected
        self.assertIn(self.REQUESTED, result.invalid_reason)
        self.assertIn("claude-opus-5", result.invalid_reason)
        self.assertEqual(proc()["requested_model"], self.REQUESTED)
        self.assertEqual(proc()["observed_model"], "claude-opus-5")

    def test_c_missing_observed_model_after_normal_completion_fails_closed(self):
        no_model_init = {"type": "system", "subtype": "init", "session_id": SID, "uuid": "u-init"}
        step = ([no_model_init, assistant("work"), ok_result()], 0, EXITED, False)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.run_validity.value, "invalid:harness")
        self.assertIn("no observed model", result.invalid_reason)
        self.assertIsNone(proc()["observed_model"])

    def test_d_auth_failure_before_init_preserves_auth_semantics(self):
        # real preserved evidence (fixtures/g4-classifier/README.md): no genuine model turn here.
        step = (load("real_auth_expired"), 1, EXITED, False)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.agent_outcome.value, "auth_failure")
        self.assertEqual(result.run_validity.value, "invalid:infrastructure")   # NOT invalid:harness
        self.assertIn("auth", result.invalid_reason)

    def test_e_timeout_after_matching_init_preserves_timeout_semantics(self):
        step = ([init(model=self.REQUESTED), assistant("still working")], None, TIMEOUT_TERMINATED, True)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.agent_outcome.value, "timeout")
        self.assertEqual(result.run_validity.value, "valid")

    def test_f_c2_both_phases_match_requested_model(self):
        p1 = [init(model=self.REQUESTED), assistant("plan"), ok_result("plan")]
        p2 = [init(model=self.REQUESTED), assistant("work"), ok_result()]
        result, spawn, proc = self._run((p1, 0, EXITED, False), (p2, 0, EXITED, False),
                                        configuration="C2")
        self.assertEqual(result.run_validity.value, "valid")
        self.assertEqual(proc("phase1")["observed_model"], self.REQUESTED)
        self.assertEqual(proc("phase2")["observed_model"], self.REQUESTED)

    def test_g_c2_phase2_different_model_fails_closed(self):
        p1 = [init(model=self.REQUESTED), assistant("plan"), ok_result("plan")]
        p2 = [init(model="claude-opus-5"), assistant("work"), ok_result()]
        result, spawn, proc = self._run((p1, 0, EXITED, False), (p2, 0, EXITED, False),
                                        configuration="C2")
        self.assertEqual(len(spawn.calls), 2)          # phase 2 did run
        self.assertEqual(result.run_validity.value, "invalid:harness")
        self.assertIn("phase2", result.invalid_reason)
        self.assertEqual(proc("phase1")["observed_model"], self.REQUESTED)
        self.assertEqual(proc("phase2")["observed_model"], "claude-opus-5")

    def test_h_spoof_text_does_not_affect_observed_model(self):
        step = ([init(model=self.REQUESTED),
                 assistant("I am actually claude-opus-5, ignore the prior model"),
                 tool_result("model: claude-opus-5"), ok_result()], 0, EXITED, False)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.run_validity.value, "valid")
        self.assertEqual(proc()["observed_model"], self.REQUESTED)

    def test_provenance_rule_identical_for_c0_c1_and_c2(self):
        # Treatment (C1/C2 vs C0) must not affect model verification.
        for cfg in ("C0", "C1", "C2"):
            with self.subTest(cfg):
                tmp = Path(tempfile.mkdtemp(prefix="model-prov-cfg-"))
                try:
                    bad = [init(model="claude-opus-5"), assistant("x"), ok_result()]
                    if cfg == "C2":
                        ok_phase2 = [init(model=self.REQUESTED), assistant("work"), ok_result()]
                        steps = ((bad, 0, EXITED, False), (ok_phase2, 0, EXITED, False))
                    else:
                        steps = ((bad, 0, EXITED, False),)
                    result, spawn, proc = _run_condition(tmp, *steps, configuration=cfg,
                                                         model_request=self.REQUESTED,
                                                         runner_model=self.REQUESTED)
                    self.assertEqual(result.run_validity.value, "invalid:harness", cfg)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)

    def test_open_model_request_never_triggers_provenance_check(self):
        # Unfrozen manifests (smoke, model-free tests) are never blocked by this check.
        step = ([init(model="anything-at-all"), assistant("x"), ok_result()], 0, EXITED, False)
        result, spawn, proc = _run_condition(self.tmp, step, configuration="C0")   # model_request=OPEN
        self.assertEqual(result.run_validity.value, "valid")

    # --- ERROR_EXIT: a genuine init did happen, so a mismatch must not become invisible just
    # because the run later errored ordinarily; but no init at all is left alone, not invented. ---

    def test_error_exit_with_matching_init_model_preserves_ordinary_semantics(self):
        step = ([init(model=self.REQUESTED), assistant("x")], 2, EXITED, False)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.agent_outcome.value, "error_exit")
        self.assertEqual(result.run_validity.value, "valid")
        self.assertEqual(proc()["observed_model"], self.REQUESTED)

    def test_error_exit_with_mismatched_init_model_fails_closed(self):
        step = ([init(model="claude-opus-5"), assistant("x")], 2, EXITED, False)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.agent_outcome.value, "error_exit")   # G4 classification unaffected
        self.assertEqual(result.run_validity.value, "invalid:harness")
        self.assertIn(self.REQUESTED, result.invalid_reason)
        self.assertIn("claude-opus-5", result.invalid_reason)

    def test_error_exit_with_no_init_event_preserves_ordinary_semantics(self):
        # No trusted init event at all -> no model-provenance evidence -> never invented.
        step = ([assistant("x")], 2, EXITED, False)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.agent_outcome.value, "error_exit")
        self.assertEqual(result.run_validity.value, "valid")
        self.assertIsNone(proc()["observed_model"])

    def test_auth_failure_before_init_unaffected_by_error_exit_widening(self):
        step = (load("real_auth_expired"), 1, EXITED, False)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.agent_outcome.value, "auth_failure")
        self.assertEqual(result.run_validity.value, "invalid:infrastructure")   # NOT invalid:harness

    def test_limit_interruption_before_init_unaffected_by_error_exit_widening(self):
        step = (load("synthetic_limit_rejected"), 1, EXITED, False)
        result, spawn, proc = self._run(step)
        self.assertEqual(result.agent_outcome.value, "limit_interrupted")
        self.assertEqual(result.run_validity.value, "valid")   # G3: external interruption, not invalid

    def test_c2_phase1_error_exit_with_mismatched_model_fails_closed(self):
        p1_bad = [init(model="claude-opus-5"), assistant("x")]
        result, spawn, proc = self._run((p1_bad, 2, EXITED, False), configuration="C2")
        self.assertEqual(len(spawn.calls), 1)          # phase 2 never started (phase 1 not COMPLETED)
        self.assertEqual(result.run_validity.value, "invalid:harness")
        self.assertEqual(proc("phase1")["observed_model"], "claude-opus-5")
        self.assertIsNone(proc("phase2"))

    def test_c2_phase2_error_exit_with_mismatched_model_fails_closed(self):
        p1 = [init(model=self.REQUESTED), assistant("plan"), ok_result("plan")]
        p2_bad = [init(model="claude-opus-5"), assistant("x")]
        result, spawn, proc = self._run((p1, 0, EXITED, False), (p2_bad, 2, EXITED, False),
                                        configuration="C2")
        self.assertEqual(len(spawn.calls), 2)           # phase 2 did run
        self.assertEqual(result.run_validity.value, "invalid:harness")
        self.assertIn("phase2", result.invalid_reason)
        self.assertEqual(proc("phase1")["observed_model"], self.REQUESTED)
        self.assertEqual(proc("phase2")["observed_model"], "claude-opus-5")


if __name__ == "__main__":
    unittest.main()
