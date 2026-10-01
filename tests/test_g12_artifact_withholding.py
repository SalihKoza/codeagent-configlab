"""G12: a secret-scan refusal of agent-side artifacts never aborts the lifecycle (model-free).

Written as ``unittest`` so it also runs under WSL's stdlib-only Python:

    PYTHONPATH=src:tests python3 -m unittest tests.test_g12_artifact_withholding -v

Only FAKE markers are used (they match the scanner's static rules); no real secret exists here.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codeagent_configlab import artifacts as art  # noqa: E402
from codeagent_configlab.artifacts import (  # noqa: E402
    ArtifactFinalizationError, ArtifactSecretError, ArtifactStore, scan_for_secrets)
from codeagent_configlab.evaluator import SmokeEvaluator  # noqa: E402
from codeagent_configlab.lifecycle import AgentRunOutcome, DryCleanupRunner, RunLifecycle  # noqa: E402
from codeagent_configlab.orchestration import snapshot_tree  # noqa: E402
from codeagent_configlab.result import audit_run_directory  # noqa: E402
from codeagent_configlab.session import SessionSpec  # noqa: E402
from codeagent_configlab.status import AgentOutcome as AO  # noqa: E402

KEY = "sk-ant-FAKE-g12-0000000000"   # fake API-key-shaped marker (static scanner rule)
CRED = ".credentials.json"           # credential file-name marker (static scanner rule)
MARKERS = (KEY, CRED, "sk-ant-")


def events(sid, text="done", tool_out="ok", is_error=False):
    return [{"type": "system", "subtype": "init", "session_id": sid},
            {"type": "assistant", "session_id": sid,
             "message": {"content": [{"type": "text", "text": text}]}},
            {"type": "user", "session_id": sid,
             "message": {"content": [{"type": "tool_result", "content": tool_out}]}},
            {"type": "result", "subtype": "success", "session_id": sid, "is_error": is_error,
             "result": text}]


class PayloadAgent:
    """Returns scripted per-invocation payloads (C2 gets two invocations)."""

    def __init__(self, *payloads, outcome=AO.COMPLETED, mutate=None):
        self.payloads, self.outcome, self.mutate, self.calls = list(payloads), outcome, mutate, 0

    def run(self, working_copy, envelope, session, *, prompt=None, deadline=None):
        p = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        if self.mutate and self.calls == len(self.payloads):
            self.mutate(working_copy.path)
        sid = session.session_id
        return AgentRunOutcome(
            exit_code=0 if self.outcome is AO.COMPLETED else 1, session_id=sid,
            agent_outcome=self.outcome, stdout=p.get("stdout", "plain stdout"),
            stderr=p.get("stderr", ""), detail=p.get("detail", ""),
            events=events(sid, p.get("text", "done"), p.get("tool", "ok")),
            process={"termination": "exited", "error": p.get("process_error")})


class CountingCleanup(DryCleanupRunner):
    def __init__(self):
        self.calls = 0

    def execute(self, plan):
        self.calls += 1
        return super().execute(plan)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g12-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_life(self, config, agent, evaluator=None):
        from _helpers import TEST_STATEMENT, make_treated_manifest, make_treatment
        from codeagent_configlab.envelope import implementation_envelope

        home = self.tmp / "home"
        (home / ".claude" / "projects").mkdir(parents=True, exist_ok=True)
        pristine = self.tmp / "pristine"
        if not pristine.exists():
            pristine.mkdir()
            (pristine / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        cleanup = self.last_cleanup = CountingCleanup()
        life = RunLifecycle(pristine=pristine, runs_root=self.tmp / f"runs-{config}",
                            results_root=self.tmp / "results", home=home)
        m = make_treated_manifest(config)
        # the real scope-guarded plan rejects temp dirs off WSL; an empty plan still proves the
        # finalization path reached the cleanup runner
        with mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan", lambda *a, **k: []):
            result = life.execute(manifest=m, envelope=implementation_envelope(config),
                                  session=SessionSpec("new", "12345678-1234-4234-8234-1234567890ab"),
                                  evaluator=evaluator or SmokeEvaluator(), agent_runner=agent,
                                  cleanup_runner=cleanup, treatment=make_treatment(config),
                                  task_statement=TEST_STATEMENT)
        run_dir = self.tmp / "results" / m.run_id
        return result, run_dir

    def stored(self, run_dir):
        return json.loads((run_dir / "result.json").read_text(encoding="utf-8"))

    def report(self, run_dir):
        p = run_dir / "artifact_report.json"
        return {e["name"]: e for e in json.loads(p.read_text())["entries"]} if p.exists() else {}

    def assertAuditableAndClean(self, run_dir):
        self.assertEqual(audit_run_directory(run_dir), [])
        self.assertEqual(self.last_cleanup.calls, 1)                       # J: cleanup ran
        for f in run_dir.rglob("*"):                                       # H/P: nothing leaked
            text = f.read_text(encoding="utf-8", errors="replace")
            for m in MARKERS:
                self.assertNotIn(m, text, f"{m!r} in {f.name}")


class Withholding(Base):
    def test_a_clean_run_is_unchanged(self):
        result, run_dir = self.run_life("C0", PayloadAgent({}))
        self.assertAuditableAndClean(run_dir)
        self.assertFalse((run_dir / "artifact_report.json").exists())
        self.assertEqual((run_dir / "stdout.txt").read_text(), "plain stdout")
        self.assertIsNone(self.stored(run_dir)["artifacts"]["artifact_report"])

    def test_b_c_d_stdout_stderr_events_withheld(self):
        payload = {"stdout": f"leak {KEY} and {KEY}", "stderr": f"cat ~/.claude/{CRED}",
                   "text": f"assistant says {KEY}", "tool": f"tool printed {CRED}"}
        result, run_dir = self.run_life("C0", PayloadAgent(payload))
        self.assertAuditableAndClean(run_dir)
        rep = self.report(run_dir)
        self.assertEqual(rep["stdout.txt"]["status"], "content_withheld")
        self.assertEqual(rep["stderr.txt"]["status"], "content_withheld")
        self.assertEqual(rep["events.jsonl"]["status"], "fields_withheld")
        for e in rep.values():
            self.assertEqual(set(e) - {"error_type"}, {"name", "status", "reason", "size_bytes",
                                                       "content_withheld"})
            self.assertEqual(e["reason"], art.CONTENT_WITHHELD)
        self.assertIn(art.CONTENT_WITHHELD, (run_dir / "stdout.txt").read_text())
        # events: structure kept, content withheld explicitly -- not an empty log
        evs = [json.loads(l) for l in (run_dir / "events.jsonl").read_text().splitlines()]
        self.assertEqual([e["type"] for e in evs], ["system", "assistant", "user", "result"])
        self.assertIs(evs[-1]["is_error"], False)
        self.assertTrue(evs[1]["message"]["content"][0]["text"].startswith("[withheld: secret-scan marker"))
        s = self.stored(run_dir)
        self.assertEqual(s["artifacts"]["stdout"], "stdout.txt")          # existed, withheld
        self.assertEqual(s["artifacts"]["artifact_report"], "artifact_report.json")
        # K: experimental outcome and eligibility untouched by withholding
        self.assertEqual((s["agent_outcome"], s["run_validity"]), ("completed", "valid"))
        self.assertEqual(s["analysis_eligibility"]["status"], "countable")

    def test_g_agent_file_content_and_names_withheld(self):
        def mutate(wc):
            (wc / "calc.py").write_text(f"KEY = '{KEY}'\n", encoding="utf-8")
            (wc / f"notes{CRED}").write_text("x\n", encoding="utf-8")
        agent = PayloadAgent({"stdout": KEY}, mutate=mutate)
        result, run_dir = self.run_life("C0", agent)
        self.assertAuditableAndClean(run_dir)
        rep = self.report(run_dir)
        self.assertEqual(rep["final.diff"]["status"], "content_withheld")
        self.assertEqual(rep["changed_files.json"]["status"], "fields_withheld")
        self.assertEqual(rep["final_state.json"]["status"], "fields_withheld")
        fs = json.loads((run_dir / "final_state.json").read_text())
        self.assertIs(fs["final_diff_withheld"], True)                      # a boolean, no marker
        self.assertEqual(self.stored(run_dir)["run_validity"], "valid")

    def test_canonical_working_copy_not_touched_by_withholding(self):
        seen = {}

        def mutate(wc):
            (wc / "calc.py").write_text(f"KEY = '{KEY}'\n", encoding="utf-8")
            seen["wc"] = wc
        result, run_dir = self.run_life("C0", PayloadAgent({}, mutate=mutate))
        self.assertIn(KEY, (seen["wc"] / "calc.py").read_text())           # agent state as left
        self.assertAuditableAndClean(run_dir)

    def test_k_other_outcomes_keep_their_semantics(self):
        for outcome, validity, elig in ((AO.TIMEOUT, "valid", "countable"),
                                        (AO.LIMIT_INTERRUPTED, "valid", "not_countable:external_interruption"),
                                        (AO.AUTH_FAILURE, "invalid:infrastructure", "not_countable:invalid")):
            with self.subTest(outcome.value):
                self.tearDown(); self.setUp()
                result, run_dir = self.run_life("C0", PayloadAgent({"stdout": KEY, "stderr": CRED},
                                                                   outcome=outcome))
                self.assertAuditableAndClean(run_dir)
                s = self.stored(run_dir)
                self.assertEqual((s["agent_outcome"], s["run_validity"], s["analysis_eligibility"]["status"]),
                                 (outcome.value, validity, elig))


class C2Phases(Base):
    def test_e_phase1_refusal_keeps_phase2(self):
        result, run_dir = self.run_life("C2", PayloadAgent({"stdout": KEY, "text": KEY}, {}))
        self.assertAuditableAndClean(run_dir)
        rep = self.report(run_dir)
        self.assertEqual(rep["phase1.stdout.txt"]["status"], "content_withheld")
        self.assertNotIn("phase2.stdout.txt", rep)
        self.assertEqual((run_dir / "phase2.stdout.txt").read_text(), "plain stdout")
        self.assertTrue((run_dir / "c2.json").exists())

    def test_f_phase2_refusal_keeps_phase1(self):
        result, run_dir = self.run_life("C2", PayloadAgent({}, {"stdout": KEY, "stderr": CRED}))
        self.assertAuditableAndClean(run_dir)
        rep = self.report(run_dir)
        self.assertEqual(rep["phase2.stdout.txt"]["status"], "content_withheld")
        self.assertEqual(rep["phase2.stderr.txt"]["status"], "content_withheld")
        self.assertEqual((run_dir / "phase1.stdout.txt").read_text(), "plain stdout")
        self.assertEqual(self.stored(run_dir)["analysis_eligibility"]["status"], "countable")

    def test_o_same_semantics_c0_c1_c2(self):
        shapes = {}
        for config in ("C0", "C1", "C2"):
            self.tearDown(); self.setUp()
            agent = PayloadAgent(*([{"stdout": KEY, "stderr": CRED, "text": KEY}] * (2 if config == "C2" else 1)))
            result, run_dir = self.run_life(config, agent)
            self.assertAuditableAndClean(run_dir)
            s = self.stored(run_dir)
            rep = self.report(run_dir)
            if config == "C2":   # C2-only layout: the phase-1 plan is its own (withheld) artifact
                self.assertEqual(rep.pop("plan.txt")["status"], "content_withheld")
            statuses = sorted({(n.split(".", 1)[-1] if n.startswith("phase") else n, e["status"])
                               for n, e in rep.items()})
            shapes[config] = (s["agent_outcome"], s["run_validity"],
                              s["analysis_eligibility"]["status"], tuple(statuses))
        self.assertEqual(len(set(shapes.values())), 1, shapes)


class StorageFailures(Base):
    def _failing_write(self, target):
        real = ArtifactStore.write_text

        def write_text(store, name, text):
            if name == target:
                raise OSError(f"disk full while writing {KEY}")          # message must not leak
            return real(store, name, text)
        return mock.patch.object(ArtifactStore, "write_text", write_text)

    def test_l_m_storage_failure_is_not_withholding_and_invalidates(self):
        with self._failing_write("stdout.txt"):
            result, run_dir = self.run_life("C0", PayloadAgent({}))
        self.assertAuditableAndClean(run_dir)
        rep = self.report(run_dir)
        self.assertEqual((rep["stdout.txt"]["status"], rep["stdout.txt"]["reason"]),
                         ("write_failed", art.WRITE_FAILED))
        self.assertIs(rep["stdout.txt"]["content_withheld"], False)
        s = self.stored(run_dir)
        self.assertEqual(s["agent_outcome"], "completed")                  # outcome untouched
        self.assertEqual(s["run_validity"], "invalid:harness")
        self.assertEqual(s["analysis_eligibility"]["status"], "not_countable:invalid")
        self.assertIn("artifact_write_failed", s["invalid_reason"])
        self.assertIsNone(s["artifacts"]["stdout"])

    def test_m_result_record_unstorable_raises_after_cleanup(self):
        with self._failing_write("result.json"):
            with self.assertRaises(ArtifactFinalizationError) as cm:
                self.run_life("C0", PayloadAgent({"stdout": KEY}))
        self.assertEqual(self.last_cleanup.calls, 1)                        # cleanup still ran
        for m in MARKERS:
            self.assertNotIn(m, str(cm.exception))

    def test_serialization_failure_code(self):
        store = ArtifactStore.create(self.tmp / "r", "x")
        e = store.write_safe("c2.json", {"bad": object()})
        self.assertEqual((e["status"], e["reason"]), ("write_failed", art.SERIALIZATION_FAILED))


class ScannerContract(unittest.TestCase):
    def test_p_scanner_error_message_never_echoes_markers(self):
        store = ArtifactStore.create(Path(tempfile.mkdtemp(prefix="g12-s-")), "x",
                                     extra_secret_markers=("REAL-LOOKING-VALUE-123",))
        try:
            with self.assertRaises(ArtifactSecretError) as cm:
                store.write_text("stdout.txt", f"{KEY} REAL-LOOKING-VALUE-123")
            msg = str(cm.exception)
            self.assertNotIn("sk-ant-", msg)
            self.assertNotIn("REAL-LOOKING-VALUE-123", msg)
            self.assertIn(art.CONTENT_WITHHELD, msg)
            # the scanner itself is unchanged (still refuses, still detects every rule)
            self.assertEqual(len(scan_for_secrets(f"{KEY} {CRED}")), 2)
            # extra markers are honoured by write_safe too
            store.write_safe("stderr.txt", "REAL-LOOKING-VALUE-123")
            self.assertNotIn("REAL-LOOKING", (store.run_dir / "stderr.txt").read_text())
        finally:
            shutil.rmtree(store.run_dir.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
