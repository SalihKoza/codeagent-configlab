"""G10: pilot-series driver -- planned cells, attempts, schedule, replacements, resume (model-free).

Written as ``unittest`` so it also runs under WSL's stdlib-only Python:

    PYTHONPATH=src:tests python3 -m unittest tests.test_series -v

Synthetic task packages (never the real P-PY-01 / P-TS-01), an injected scripted agent and the
offline FakeSandbox evaluator wrapper. No Claude call, no srt.
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

from _helpers import FakeSandbox, TEST_APPROVAL, TEST_CLAUDE_MD, TEST_WRAPPER  # noqa: E402

from codeagent_configlab.evaluator import EvaluationResult  # noqa: E402
from codeagent_configlab.lifecycle import AgentRunOutcome  # noqa: E402
from codeagent_configlab.series import (  # noqa: E402
    Series, SeriesConfig, SeriesError, SeriesFrozenError, SeriesNotReady, SeriesStateError,
    assert_promotable_to_final, build_spec, frozen_cell_spec_hash, generate_schedule,
    load_pilot_attempt, readiness_errors, replacement_decision)
from codeagent_configlab.status import Acceptance, AgentOutcome as AO, Regression  # noqa: E402
from codeagent_configlab.task_evaluator import TaskEvaluator  # noqa: E402
from codeagent_configlab.task_package import TaskPackage  # noqa: E402

PY = sys.executable
MODEL = "synthetic-model-for-tests"    # NOT a model choice; any concrete string
EFFORT = "high"                        # NOT an effort choice; any concrete string


def make_package(root: Path, task_id: str, gate="PASS") -> Path:
    pkg = root / task_id
    (pkg / "pristine").mkdir(parents=True)
    (pkg / "pristine" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (pkg / "hidden").mkdir()
    (pkg / "hidden" / "check.py").write_text(
        "import os, sys\nsys.path.insert(0, os.getcwd())\nimport calc\nassert calc.multiply(3, 4) == 12\n")
    (pkg / "statement.md").write_text(f"[{task_id}] Add multiply(a, b) to calc.py.\n", encoding="utf-8")
    meta = {"task_id": task_id, "language": "python", "task_category": "feature",
            "statement": "statement.md", "pristine": "pristine", "hidden": "hidden",
            "evaluator": {"acceptance": [{"name": "hidden", "argv": [PY, "_hidden_tests/check.py"],
                                          "timeout_seconds": 60}],
                          "regression": [{"name": "add", "argv": [PY, "-c",
                                          "import calc; assert calc.add(2, 3) == 5"],
                                          "timeout_seconds": 60}],
                          "protected_paths": []},
            "validity_gate": {"status": gate, "task_version_hash": None, "evidence_ref": "synthetic"}}
    (pkg / "package.json").write_text(json.dumps(meta), encoding="utf-8")
    meta["validity_gate"]["task_version_hash"] = TaskPackage.load(pkg).version_hash()
    (pkg / "package.json").write_text(json.dumps(meta), encoding="utf-8")
    return pkg


def add_multiply(wc: Path):
    (wc / "calc.py").write_text("def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n")


class FakeCleanupRunner:
    """A non-Dry, in-process CleanupRunner double (no subprocess). Records every plan it was
    asked to execute; ``ok`` controls whether it reports success, and ``leave_residue`` simulates
    a command that reports success (exit 0) but did not actually remove its own target -- exactly
    the class of bug ``verify_residue`` exists to catch."""

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


class FakeAgentRunnerForCli:
    """Stand-in for ``runners.RealAgentRunner`` with the identical constructor signature
    ``_production_factories``'s ``runner_factory`` calls, so the CLI wiring itself can be
    exercised without a real ``claude``/``srt`` invocation."""

    def __init__(self, home, harness_root, model, effort, prompt):
        self.home, self.harness_root, self.model, self.effort, self.prompt = (
            home, harness_root, model, effort, prompt)

    def run(self, working_copy, envelope, session, *, prompt=None, deadline=None):
        sid = session.session_id
        if envelope.phase == "implementation":
            add_multiply(working_copy.path)
        return AgentRunOutcome(
            exit_code=0, session_id=sid, agent_outcome=AO.COMPLETED, stdout="ok",
            events=[{"type": "system", "subtype": "init", "session_id": sid, "model": self.model},
                    {"type": "result", "subtype": "success", "session_id": sid, "is_error": False}],
            observed_model=self.model)


def _unsafe_build_cleanup_plan_for_tests(working_copy, session_uuids, *, uid, home):
    """Same argv shape as ``cleanup.build_cleanup_plan``, without its hardcoded-``/home/cclab``
    scope guard -- tests use a synthetic tmp-path home (never the real ``/home/cclab`` this very
    session runs under), so the guard would otherwise reject every target regardless of intent.
    Production code always goes through the real, guarded ``build_cleanup_plan``; this stand-in
    is only ever monkeypatched in for these tests."""
    from codeagent_configlab.cleanup import CleanupCommand, wc_slug

    plan = [CleanupCommand(argv=("claude", "project", "purge", "-y", working_copy),
                           purpose="remove project transcripts/memory/config entry for this working copy")]
    for u in session_uuids:
        plan.append(CleanupCommand(argv=("rm", "-rf", "--", f"{home}/.claude/session-env/{u}"),
                                   purpose=f"remove exact session-env dir for {u}"))
    plan.append(CleanupCommand(argv=("rm", "-rf", "--", f"/tmp/claude/claude-{uid}/{wc_slug(working_copy)}"),
                               purpose="remove exact per-project /tmp/claude dir"))
    return plan


def fake_evaluator_for(series, pkg):
    """Stand-in for ``__main__._evaluator_for``: real TaskEvaluator logic, FakeSandbox only."""

    class Ev:
        def evaluate(self, wc):
            return TaskEvaluator(pkg.evaluator_spec(), sandbox=FakeSandbox()).evaluate(wc)
    return Ev()


class ScriptedAgent:
    """Per-manifest behavior: outcome + whether it solves the task. Records deadlines received."""

    def __init__(self, manifest, plan, log):
        self.manifest, self.model = manifest, manifest.model_request
        self.effort = manifest.effort_request
        self.outcome, self.solve = plan.get((manifest.task_id, manifest.configuration,
                                             manifest.attempt_ordinal), (AO.COMPLETED, True))
        self.log = log

    def run(self, working_copy, envelope, session, *, prompt=None, deadline=None):
        self.log.append({"attempt": self.manifest.run_id, "phase": envelope.phase,
                         "budget": None if deadline is None else deadline.budget_seconds,
                         "cwd": str(working_copy.path),
                         "model": self.model, "effort": self.effort,
                         "configuration": self.manifest.configuration})
        if self.solve and envelope.phase == "implementation":
            add_multiply(working_copy.path)
        sid = session.session_id
        return AgentRunOutcome(
            exit_code=0 if self.outcome is AO.COMPLETED else (None if self.outcome is AO.TIMEOUT else 1),
            session_id=sid, agent_outcome=self.outcome, stdout="ok", detail="scripted",
            events=[{"type": "system", "subtype": "init", "session_id": sid, "model": self.model},
                    {"type": "result", "subtype": "success", "session_id": sid, "is_error": False,
                     "result": "plan text"}],
            observed_model=self.model)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g10-"))
        self.harness = self.tmp / "harness"
        pk = self.harness / "packages"
        self.pkgs = [make_package(pk, "P-SYN-A"), make_package(pk, "P-SYN-B")]
        tr = self.harness / "treatments"
        tr.mkdir(parents=True)
        (tr / "CLAUDE.md").write_bytes(TEST_CLAUDE_MD)
        (tr / "wrapper.txt").write_text(TEST_WRAPPER, encoding="utf-8")
        (tr / "approval.txt").write_text(TEST_APPROVAL, encoding="utf-8")
        self.home = self.tmp / "home"
        (self.home / ".claude" / "projects").mkdir(parents=True)
        self.plan, self.agent_log = {}, []
        self.evaluator_errors = set()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def config(self, **over):
        tr = self.harness / "treatments"
        base = dict(pilot_version="pilot-test", package_dirs=[str(p) for p in self.pkgs],
                    model_request=MODEL, effort_request=EFFORT, timeout_seconds=600,
                    claude_md_file=str(tr / "CLAUDE.md"), planning_wrapper_file=str(tr / "wrapper.txt"),
                    approval_message_file=str(tr / "approval.txt"))
        base.update(over)
        return SeriesConfig(**base)

    def series(self, config=None) -> Series:
        return Series(root=self.harness / "series" / "pilot-test", config=config or self.config(),
                      harness_root=self.harness, home=self.home)

    def runner_factory(self, manifest):
        return ScriptedAgent(manifest, self.plan, self.agent_log)

    def evaluator_factory(self, pkg):
        s = self

        class Ev:
            def evaluate(self, wc):
                if s.evaluator_errors and "all" in s.evaluator_errors:
                    return EvaluationResult(Acceptance.ERROR, Regression.ERROR, evaluator_error=True,
                                            detail="simulated sandbox failure")
                return TaskEvaluator(pkg.evaluator_spec(), sandbox=FakeSandbox()).evaluate(wc)
        return Ev()

    def step(self, s):
        return s.execute_next(self.runner_factory, self.evaluator_factory)


class ManifestExecution(Base):
    def test_a_b_c_manifest_timeout_is_the_budget(self):
        s = self.series()
        s.freeze()
        for _ in range(6):
            self.step(s)
        by_attempt = {}
        for e in self.agent_log:
            by_attempt.setdefault(e["attempt"], []).append(e)
        for calls in by_attempt.values():
            if len(calls) == 1:                                       # C0 / C1
                self.assertEqual(calls[0]["budget"], 600.0)
            else:                                                     # C2: one shared budget
                self.assertEqual(calls[0]["budget"], 600.0)
                self.assertLessEqual(calls[1]["budget"], 600.0)
        self.assertEqual(sum(len(c) for c in by_attempt.values()), 8)  # 2 C2 x 2 phases + 4

    def test_c0_c1_c2_and_both_c2_phases_share_model_and_effort(self):
        s = self.series()
        s.freeze()
        for _ in range(6):
            self.step(s)
        by_attempt = {}
        for e in self.agent_log:
            by_attempt.setdefault(e["attempt"], []).append(e)
        seen_configs = set()
        for calls in by_attempt.values():
            seen_configs.add(calls[0]["configuration"])
            for c in calls:
                # Every C0/C1/C2 invocation, both C2 phases included, uses the one frozen
                # model/effort pair -- no per-configuration or per-phase divergence is possible.
                self.assertEqual(c["model"], MODEL)
                self.assertEqual(c["effort"], EFFORT)
            if len(calls) == 2:                                       # C2: same runner object
                self.assertEqual(calls[0]["model"], calls[1]["model"])
                self.assertEqual(calls[0]["effort"], calls[1]["effort"])
        self.assertEqual(seen_configs, {"C0", "C1", "C2"})

    def test_d_e_open_values_block_execution_but_not_planning(self):
        for over, needle in (({"timeout_seconds": "OPEN"}, "timeout"), ({"model_request": "OPEN"}, "model"),
                             ({"effort_request": "OPEN"}, "effort")):
            with self.subTest(needle):
                self.tearDown(); self.setUp()
                s = self.series(self.config(**over))
                s.freeze()
                plan = s.plan_next()
                self.assertIsNotNone(plan["next"])
                self.assertTrue(any(needle in e for e in plan["readiness_errors"]))
                with self.assertRaises(SeriesNotReady):
                    self.step(s)
                self.assertFalse(s.attempts_root.exists())            # nothing created
                self.assertEqual(s.events(), [])

    def test_f_changed_hashes_fail_closed(self):
        s = self.series()
        s.freeze()
        self.step(s)
        (self.harness / "treatments" / "CLAUDE.md").write_bytes(b"# changed\n")
        with self.assertRaises(SeriesFrozenError):
            self.step(s)
        (self.harness / "treatments" / "CLAUDE.md").write_bytes(TEST_CLAUDE_MD)
        (self.pkgs[0] / "hidden" / "check.py").write_text("assert True\n")   # package mutated
        with self.assertRaises(SeriesFrozenError):
            self.step(s)
        for over in ({"model_request": "other"}, {"timeout_seconds": 601}, {"effort_request": "low"}):
            with self.assertRaises(SeriesFrozenError):
                Series(root=s.root, config=self.config(**over), harness_root=self.harness,
                       home=self.home).execute_next(self.runner_factory, self.evaluator_factory)

    def test_gate_not_passed_blocks(self):
        pkg = make_package(self.tmp / "other", "P-SYN-C", gate="FAIL")
        s = self.series(self.config(package_dirs=[str(self.pkgs[0]), str(pkg)]))
        s.freeze()
        with self.assertRaises(SeriesNotReady):
            self.step(s)

    def test_manifest_is_authoritative_in_lifecycle(self):
        from _helpers import TEST_STATEMENT, make_treated_manifest
        from codeagent_configlab.envelope import implementation_envelope
        from codeagent_configlab.lifecycle import RunLifecycle
        from codeagent_configlab.session import SessionSpec

        m = make_treated_manifest("C0", timeout_seconds=100, model_request=MODEL)
        life = RunLifecycle(pristine=self.pkgs[0] / "pristine", runs_root=self.tmp / "r",
                            results_root=self.tmp / "res", home=self.home)
        kw = dict(manifest=m, envelope=implementation_envelope("C0"),
                  session=SessionSpec("new", "12345678-1234-4234-8234-123456789abc"),
                  evaluator=self.evaluator_factory(TaskPackage.load(self.pkgs[0])),
                  task_statement=TEST_STATEMENT)
        with self.assertRaises(ValueError):                           # hidden budget override
            life.execute(agent_runner=ScriptedAgent(m, {}, []), budget_seconds=5, **kw)
        other = ScriptedAgent(m, {}, [])
        other.model = "another-model"
        with self.assertRaises(ValueError):                           # runner model != manifest
            life.execute(agent_runner=other, **kw)

        m_eff = make_treated_manifest("C0", timeout_seconds=100, model_request=MODEL,
                                      effort_request=EFFORT)
        kw_eff = {**kw, "manifest": m_eff}
        other_eff = ScriptedAgent(m_eff, {}, [])
        other_eff.effort = "another-effort"
        with self.assertRaises(ValueError):                           # runner effort != manifest
            life.execute(agent_runner=other_eff, **kw_eff)

        self.assertFalse((self.tmp / "res").exists())                 # refused before anything
        s = self.series()
        s.freeze()
        with self.assertRaises(SeriesFrozenError):
            s.execute_next(lambda man: other, self.evaluator_factory)
        self.assertEqual(s.events(), [])                              # not recorded as started


class Schedule(Base):
    def test_g_to_l_deterministic_interleaved_complete(self):
        spec = build_spec(self.config())
        a, b = generate_schedule(spec), generate_schedule(spec)
        self.assertEqual(a, b)                                        # G
        cells = a["cells"]
        self.assertEqual(len(cells), 6)                               # I
        self.assertEqual(len({c["cell_id"] for c in cells}), 6)
        self.assertEqual({(c["task_id"], c["configuration"]) for c in cells},
                         {(t, c) for t in ("P-SYN-A", "P-SYN-B") for c in ("C0", "C1", "C2")})  # J
        tasks = [c["task_id"] for c in cells]
        self.assertEqual(tasks[0::2], [tasks[0]] * 3)                 # §6 alternation t1,t2,t1,...
        self.assertEqual(tasks[1::2], [tasks[1]] * 3)
        self.assertNotEqual(tasks[0], tasks[1])
        p1 = [c["configuration"] for c in cells[0::2]]
        p2 = [c["configuration"] for c in cells[1::2]]
        self.assertNotEqual(p1, p2)                                   # permutations differ
        self.assertTrue(all(c["repetition"] == 1 for c in cells))

    def test_h_seed_changes_order(self):
        orders = {tuple(c["cell_id"] for c in generate_schedule(
            build_spec(self.config(order_seed_text=f"seed-{i}")))["cells"]) for i in range(12)}
        self.assertGreater(len(orders), 1)

    def test_k_l_schedule_persisted_and_outcome_independent(self):
        s = self.series()
        s.freeze()
        before = json.loads((s.root / "schedule.json").read_text())
        self.plan[("P-SYN-A", "C0", 1)] = (AO.LIMIT_INTERRUPTED, False)
        for _ in range(6):
            self.step(s)
        after = json.loads((s.root / "schedule.json").read_text())
        self.assertEqual(before, after)                               # K/L
        self.assertEqual(s.freeze()["already_frozen"], True)
        self.assertEqual([st["position"] for st in s.status()["cells"]], [1, 2, 3, 4, 5, 6])


class AttemptsAndReplacements(Base):
    def run_all(self, s):
        out = []
        while True:
            r = self.step(s)
            if r.get("done"):
                return out
            out.append(r)

    def states(self, s):
        return {(c["task_id"], c["configuration"]): c["state"] for c in s.status()["cells"]}

    def test_m_n_o_legitimate_outcomes_are_complete(self):
        self.plan[("P-SYN-A", "C0", 1)] = (AO.COMPLETED, False)     # N: acceptance fail
        self.plan[("P-SYN-A", "C1", 1)] = (AO.TIMEOUT, False)       # O: valid timeout
        self.plan[("P-SYN-B", "C0", 1)] = (AO.ERROR_EXIT, False)    # error_exit
        s = self.series()
        s.freeze()
        res = self.run_all(s)
        self.assertEqual(len(res), 6)                                 # no replacement ran
        self.assertTrue(all(r["decision"] == "complete" for r in res))
        self.assertEqual(set(self.states(s).values()), {"observed"})
        rec = next(r["record"] for r in res if r["record"]["agent_outcome"] == "completed"
                   and r["record"]["acceptance"] == "fail")
        self.assertEqual(rec["analysis_eligibility"]["status"], "countable")

    def test_p_q_s_t_v_replacement_requires_approval_and_links(self):
        self.plan[("P-SYN-A", "C1", 1)] = (AO.LIMIT_INTERRUPTED, False)
        self.plan[("P-SYN-B", "C2", 1)] = (AO.AUTH_FAILURE, False)
        s = self.series()
        s.freeze()
        res = self.run_all(s)
        self.assertEqual(len(res), 6)                                 # never automatic
        st = self.states(s)
        self.assertEqual(st[("P-SYN-A", "C1")], "replacement_eligible")   # P
        self.assertEqual(st[("P-SYN-B", "C2")], "replacement_eligible")   # Q
        with self.assertRaises(SeriesStateError):                     # countable cell: never
            s.approve_replacement(next(c["cell_id"] for c in s.status()["cells"]
                                       if c["state"] == "observed"), "no")
        views = s.cells()
        lim_cell = next(cid for cid, v in views.items() if v.cell["task_id"] == "P-SYN-A"
                        and v.cell["configuration"] == "C1")
        s.approve_replacement(lim_cell, "limit reset", "operator checked the reset time")
        r = self.step(s)
        self.assertEqual((r["kind"], r["ordinal"], r["cell_id"]), ("replacement", 2, lim_cell))
        run_dir = s.attempts_root / r["executed"]
        m = load_pilot_attempt(run_dir)
        first = views[lim_cell].attempts[0]["started"]["attempt_id"]
        self.assertEqual((m["cell_id"], m["original_attempt_id"], m["predecessor_attempt_id"],
                          m["attempt_kind"], m["repetition"], m["replacement_reason"]),
                         (lim_cell, first, first, "replacement", 1, "limit reset"))   # S / V
        orig = json.loads((s.attempts_root / first / "manifest.json").read_text())
        from codeagent_configlab.manifest import RunManifest
        self.assertEqual(frozen_cell_spec_hash(RunManifest.from_dict(orig)),
                         frozen_cell_spec_hash(RunManifest.from_dict(m)))            # T
        self.assertEqual(self.states(s)[("P-SYN-A", "C1")], "observed")
        self.assertTrue((s.attempts_root / first / "result.json").exists())           # Y kept

    def test_v_at_most_one_replacement(self):
        self.plan[("P-SYN-A", "C0", 1)] = (AO.LIMIT_INTERRUPTED, False)
        self.plan[("P-SYN-A", "C0", 2)] = (AO.LIMIT_INTERRUPTED, False)
        s = self.series()
        s.freeze()
        self.run_all(s)
        cid = next(c["cell_id"] for c in s.status()["cells"] if c["state"] == "replacement_eligible")
        s.approve_replacement(cid, "limit reset")
        self.step(s)
        self.assertEqual(self.states(s)[("P-SYN-A", "C0")], "no_valid_attempt")
        with self.assertRaises(SeriesStateError):
            s.approve_replacement(cid, "again")
        self.assertTrue(self.step(s)["done"])

    def test_r_evaluation_pending_is_reevaluated_not_rerun(self):
        self.evaluator_errors.add("all")
        s = self.series()
        s.freeze()
        r = self.step(s)
        self.assertEqual(r["decision"], "reevaluate")
        views = s.cells()
        self.assertEqual(views[r["cell_id"]].state, "evaluation_pending")
        with self.assertRaises(SeriesStateError):
            s.approve_replacement(r["cell_id"], "no")                 # not a replacement case
        self.evaluator_errors.clear()
        pkg = TaskPackage.load(next(p for p in self.pkgs if p.name == views[r["cell_id"]].cell["task_id"]))
        ev = s.reevaluate(r["executed"], TaskEvaluator(pkg.evaluator_spec(), sandbox=FakeSandbox()))
        self.assertEqual(ev["analysis_eligibility"]["status"], "countable")
        self.assertEqual(s.cells()[r["cell_id"]].state, "observed")
        self.assertEqual(len(s.cells()[r["cell_id"]].attempts), 1)   # no second agent attempt
        run_dir = s.attempts_root / r["executed"]
        self.assertTrue(json.loads((run_dir / "result.json").read_text())["evaluator_error"])  # untouched
        self.assertEqual(len(json.loads((run_dir / "reevaluation.json").read_text())), 1)

    def test_halt_decisions(self):
        base = {"analysis_eligibility": {"status": "not_countable:invalid"}, "c2_protocol": None}
        for validity, expected in (("invalid:leak", "halt"), ("invalid:carryover", "halt"),
                                   ("invalid:treatment_drift", "not_eligible"),
                                   ("invalid:fixture", "eligible_operator_confirm"),
                                   ("preflight_failed", "eligible"), ("invalid:harness", "eligible")):
            self.assertEqual(replacement_decision({**base, "run_validity": validity}), expected)
        self.assertEqual(replacement_decision({**base, "run_validity": "invalid:c2_protocol",
                                               "c2_protocol": "phase1_write"}), "halt")
        for status in ("countable",):
            self.assertEqual(replacement_decision({"analysis_eligibility": {"status": status},
                                                   "run_validity": "valid"}), "complete")

    # -------------------------------------------------------- cleanup wiring/reconciliation --

    def test_real_cleanup_failure_invalidates_and_halts_series(self):
        s = self.series()
        s.freeze()
        fake = FakeCleanupRunner(ok=False)
        with mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan",
                        _unsafe_build_cleanup_plan_for_tests):
            r = s.execute_next(self.runner_factory, self.evaluator_factory, cleanup_runner=fake)
        self.assertEqual(len(fake.calls), 1)                          # cleanup was actually invoked
        self.assertEqual(r["record"]["run_validity"], "invalid:harness")
        self.assertTrue(r["record"]["invalid_reason"].startswith("cleanup_failed:"))
        self.assertEqual(r["record"]["analysis_eligibility"]["status"], "not_countable:invalid")
        self.assertTrue(s.halted())
        with self.assertRaises(SeriesStateError):
            s.plan_next()                                             # cell 2 cannot run
        self.assertEqual(s.cells()[r["cell_id"]].state, "replacement_eligible")

    def test_real_cleanup_success_but_leftover_residue_still_invalidates(self):
        s = self.series()
        s.freeze()
        fake = FakeCleanupRunner(ok=True, leave_residue=True)
        with mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan",
                        _unsafe_build_cleanup_plan_for_tests):
            r = s.execute_next(self.runner_factory, self.evaluator_factory, cleanup_runner=fake)
        self.assertEqual(r["record"]["run_validity"], "invalid:harness")
        self.assertTrue(r["record"]["invalid_reason"].startswith("cleanup_failed:"))
        self.assertTrue(s.halted())

    def test_successful_real_cleanup_records_performed_true_and_stays_valid(self):
        s = self.series()
        s.freeze()
        fake = FakeCleanupRunner(ok=True)
        with mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan",
                        _unsafe_build_cleanup_plan_for_tests):
            r = s.execute_next(self.runner_factory, self.evaluator_factory, cleanup_runner=fake)
        self.assertEqual(len(fake.calls), 1)
        run_dir = s.attempts_root / r["executed"]
        res = json.loads((run_dir / "result.json").read_text())
        self.assertTrue(res["cleanup"]["performed"])
        self.assertEqual(res["run_validity"], "valid")
        self.assertFalse(s.halted())
        self.assertEqual(s.cells()[r["cell_id"]].state, "observed")

    def test_dry_cleanup_never_halts_or_invalidates_existing_tests(self):
        # regression guard: every pre-existing execute_next() call in this file passes no
        # cleanup_runner at all (defaults to None -> Dry inside the lifecycle); none of them
        # should be affected by the new cleanup-failure invariant.
        s = self.series()
        s.freeze()
        for _ in range(6):
            self.step(s)
        self.assertFalse(s.halted())
        self.assertEqual(set(self.states(s).values()), {"observed"})

    def test_remediate_cleanup_end_to_end_matches_production_defect(self):
        # Base.step() uses no cleanup_runner -> Dry -> exactly the historical production defect.
        s = self.series()
        s.freeze()
        r = self.step(s)
        self.assertEqual(s.cells()[r["cell_id"]].state, "observed")   # looked fine before the fix
        run_dir = s.attempts_root / r["executed"]
        before = (run_dir / "result.json").read_text()
        cleanup_report = {"commands": [], "executed": True, "cleanup_failed": False,
                          "residue": {"targets": [], "all_clear": True}}
        ev = s.remediate_cleanup(r["executed"], cleanup_report=cleanup_report,
                                 reason="historical DryCleanupRunner defect")
        self.assertEqual(ev["run_validity"], "invalid:harness")
        self.assertEqual(ev["analysis_eligibility"]["status"], "not_countable:invalid")
        self.assertEqual((run_dir / "result.json").read_text(), before)   # original evidence untouched
        self.assertEqual(s.cells()[r["cell_id"]].state, "replacement_eligible")
        self.assertTrue(s.halted())
        with self.assertRaises(SeriesStateError):
            s.plan_next()                                                # cell 2 cannot run
        with self.assertRaises(SeriesStateError):
            s.execute_next(self.runner_factory, self.evaluator_factory)  # halted: refused outright

    def test_remediate_cleanup_refuses_double_remediation(self):
        s = self.series()
        s.freeze()
        r = self.step(s)
        cleanup_report = {"commands": [], "executed": True, "cleanup_failed": False}
        s.remediate_cleanup(r["executed"], cleanup_report=cleanup_report, reason="first")
        with self.assertRaises(SeriesStateError):
            s.remediate_cleanup(r["executed"], cleanup_report=cleanup_report, reason="second")

    def test_remediate_cleanup_refuses_when_original_cleanup_already_succeeded(self):
        s = self.series()
        s.freeze()
        fake = FakeCleanupRunner(ok=True)
        with mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan",
                        _unsafe_build_cleanup_plan_for_tests):
            r = s.execute_next(self.runner_factory, self.evaluator_factory, cleanup_runner=fake)
        with self.assertRaises(SeriesStateError):
            s.remediate_cleanup(r["executed"], cleanup_report={"executed": True}, reason="not needed")

    def test_remediate_cleanup_refuses_non_last_attempt(self):
        self.plan[("P-SYN-A", "C1", 1)] = (AO.LIMIT_INTERRUPTED, False)
        s = self.series()
        s.freeze()
        self.run_all(s)
        lim_cell = next(cid for cid, v in s.cells().items()
                        if v.cell["task_id"] == "P-SYN-A" and v.cell["configuration"] == "C1")
        first_attempt = s.cells()[lim_cell].attempts[0]["started"]["attempt_id"]
        s.approve_replacement(lim_cell, "limit reset", "operator checked the reset time")
        self.step(s)                                                   # replacement attempt now runs
        with self.assertRaises(SeriesStateError):
            s.remediate_cleanup(first_attempt, cleanup_report={"executed": True}, reason="wrong attempt")


class ResumeAndCrash(Base):
    def test_w_x_aa_resume_continues_in_order(self):
        s = self.series()
        s.freeze()
        first_two = [self.step(s)["cell_id"] for _ in range(2)]
        s2 = self.series()                                            # fresh process view
        plan = s2.plan_next()
        self.assertEqual(plan["next"]["position"], 3)
        rest = []
        while True:
            r = s2.execute_next(self.runner_factory, self.evaluator_factory)
            if r.get("done"):
                break
            rest.append(r["cell_id"])
        sched = [c["cell_id"] for c in json.loads((s.root / "schedule.json").read_text())["cells"]]
        self.assertEqual(first_two + rest, sched)                     # AA
        self.assertEqual(len([e for e in s2.events() if e["event"] == "attempt_started"]), 6)  # X

    def test_z_crash_between_start_and_finish_is_detected(self):
        s = self.series()
        s.freeze()
        r = self.step(s)
        # simulate a driver crash: the lifecycle finished but the finish event was never written
        lines = (s.root / "events.jsonl").read_text().splitlines()
        (s.root / "events.jsonl").write_text("\n".join(lines[:-1]) + "\n")
        self.assertEqual(s.cells()[r["cell_id"]].state, "ambiguous")
        with self.assertRaises(SeriesStateError):
            self.step(s)                                              # never silently re-run
        with self.assertRaises(SeriesStateError):
            s.plan_next()
        ev = s.recover(r["executed"])
        self.assertTrue(ev["recovered"])
        self.assertEqual(s.cells()[r["cell_id"]].state, "observed")
        starts = [e["attempt_id"] for e in s.events() if e["event"] == "attempt_started"]
        self.assertEqual(starts, [r["executed"]])

    def test_z_crash_without_result_becomes_aborted_attempt(self):
        s = self.series()
        s.freeze()
        r = self.step(s)
        lines = (s.root / "events.jsonl").read_text().splitlines()
        (s.root / "events.jsonl").write_text("\n".join(lines[:-1]) + "\n")
        (s.attempts_root / r["executed"] / "result.json").unlink()
        ev = s.recover(r["executed"])
        self.assertEqual(ev["event"], "attempt_aborted")
        self.assertEqual(s.cells()[r["cell_id"]].state, "replacement_eligible")


class Namespaces(Base):
    def test_ab_ac_smoke_and_pilot_guards(self):
        from codeagent_configlab.smoke import build_smoke_manifest

        d = self.tmp / "smoke-run"
        d.mkdir()
        (d / "manifest.json").write_text(json.dumps(build_smoke_manifest().to_dict()))
        with self.assertRaises(SeriesError):
            load_pilot_attempt(d)                                     # AB
        s = self.series()
        s.freeze()
        r = self.step(s)
        m = load_pilot_attempt(s.attempts_root / r["executed"])
        with self.assertRaises(SeriesError):
            assert_promotable_to_final(m)                             # AC
        with self.assertRaises(SeriesError):
            build_spec(self.config(namespace="FINAL"))

    def test_ad_ae_workspace_is_opaque(self):
        s = self.series()
        s.freeze()
        r = self.step(s)
        m = load_pilot_attempt(s.attempts_root / r["executed"])
        wc = s.runs_root / m["workspace_token"]
        self.assertTrue(wc.is_dir())
        for needle in (m["cell_id"], m["task_id"], "pilot-test", r["executed"], "P-SYN"):
            self.assertNotIn(needle, wc.name)
        for f in wc.rglob("*"):
            if f.is_file() and ".git" not in f.parts:
                text = f.read_text(encoding="utf-8", errors="replace")
                for needle in (m["cell_id"], "pilot-test", "spec_hash", "schedule"):
                    self.assertNotIn(needle, text, f)
        self.assertFalse(str(s.root).startswith(str(wc)))


class Cli(Base):
    def test_cli_dry_commands_and_refusals(self):
        import contextlib
        import io

        from codeagent_configlab.__main__ import main

        cfg = {"pilot_version": "pilot-test", "package_dirs": [str(p) for p in self.pkgs],
               "claude_md_file": str(self.harness / "treatments" / "CLAUDE.md")}   # model/timeout OPEN
        path = self.tmp / "series.json"
        path.write_text(json.dumps(cfg))
        common = ["--config", str(path), "--harness-root", str(self.harness), "--home", str(self.home)]

        def run(*a):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["series", *a, *common])
            return code, json.loads(buf.getvalue())

        self.assertEqual(run("freeze")[0], 0)
        code, plan = run("plan")
        self.assertEqual(code, 0)
        self.assertEqual((plan["model_request_frozen"], plan["timeout_frozen"]), (False, False))
        self.assertEqual(plan["next"]["position"], 1)
        self.assertEqual(run("status")[1]["cells"][0]["state"], "pending")
        self.assertEqual(run("run-next")[0], 2)                      # needs --execute
        code, out = run("run-next", "--execute")                     # refused: not ready
        self.assertEqual((code, out["error"]), (2, "SeriesNotReady"))
        series_root = self.harness / "series" / "pilot-test"
        self.assertFalse((series_root / "attempts").exists())
        self.assertFalse((series_root / "events.jsonl").exists())

    def _ready_series_json(self):
        cfg = self.config()
        path = self.tmp / "series.json"
        path.write_text(json.dumps({
            "pilot_version": cfg.pilot_version, "package_dirs": [str(p) for p in self.pkgs],
            "model_request": cfg.model_request, "effort_request": cfg.effort_request,
            "timeout_seconds": cfg.timeout_seconds, "claude_md_file": cfg.claude_md_file,
            "planning_wrapper_file": cfg.planning_wrapper_file,
            "approval_message_file": cfg.approval_message_file}))
        common = ["--config", str(path), "--harness-root", str(self.harness), "--home", str(self.home)]

        def run(*a):
            import contextlib
            import io

            from codeagent_configlab.__main__ import main

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["series", *a, *common])
            return code, json.loads(buf.getvalue())
        return run

    def test_run_next_execute_wires_a_real_non_dry_cleanup_runner(self):
        # This is the direct regression test for the production defect: run-next --execute must
        # construct and pass a real (non-Dry) CleanupRunner, never rely on the None/Dry default.
        run = self._ready_series_json()
        self.assertEqual(run("freeze")[0], 0)

        constructed = []

        class RecordingCleanupRunner(FakeCleanupRunner):
            def __init__(self, home):
                super().__init__(ok=True)
                constructed.append(self)

        with mock.patch("codeagent_configlab.runners.RealAgentRunner", FakeAgentRunnerForCli), \
             mock.patch("codeagent_configlab.runners.RealCleanupRunner", RecordingCleanupRunner), \
             mock.patch("codeagent_configlab.__main__._evaluator_for", fake_evaluator_for), \
             mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan",
                        _unsafe_build_cleanup_plan_for_tests):
            code, out = run("run-next", "--execute")

        self.assertEqual(code, 0, out)
        self.assertEqual(len(constructed), 1)                # RealCleanupRunner was constructed
        self.assertEqual(len(constructed[0].calls), 1)        # ... and actually invoked
        self.assertEqual(run("status")[1]["cells"][0]["state"], "observed")
        self.assertTrue(json.loads((self.harness / "series" / "pilot-test" / "attempts"
                                    / out["executed"] / "result.json").read_text())["cleanup"]["performed"])

    def test_run_next_execute_now_fails_closed_on_a_real_cleanup_failure(self):
        run = self._ready_series_json()
        self.assertEqual(run("freeze")[0], 0)
        with mock.patch("codeagent_configlab.runners.RealAgentRunner", FakeAgentRunnerForCli), \
             mock.patch("codeagent_configlab.runners.RealCleanupRunner",
                        lambda home: FakeCleanupRunner(ok=False)), \
             mock.patch("codeagent_configlab.__main__._evaluator_for", fake_evaluator_for), \
             mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan",
                        _unsafe_build_cleanup_plan_for_tests):
            code, out = run("run-next", "--execute")
        self.assertEqual(code, 0)
        self.assertEqual(out["record"]["run_validity"], "invalid:harness")
        self.assertTrue(out["record"]["invalid_reason"].startswith("cleanup_failed:"))
        self.assertTrue(run("status")[1]["halted"])

    def test_cli_remediate_cleanup_dispatches_to_series_and_halts(self):
        # Build the DISTINCT historical shape remediate-cleanup exists for: an attempt whose
        # original cleanup never ran (Dry, the pre-fix production defect) yet was left
        # valid/observed -- via Series directly, bypassing the CLI's now-fixed run-next wiring.
        run = self._ready_series_json()
        self.assertEqual(run("freeze")[0], 0)
        from codeagent_configlab.series import Series
        s = Series(root=self.harness / "series" / "pilot-test", config=self.config(),
                  harness_root=self.harness, home=self.home)
        r = s.execute_next(self.runner_factory, self.evaluator_factory)   # no cleanup_runner -> Dry
        self.assertEqual(s.cells()[r["cell_id"]].state, "observed")

        with mock.patch("codeagent_configlab.runners.RealCleanupRunner",
                        lambda home: FakeCleanupRunner(ok=True)), \
             mock.patch("codeagent_configlab.cleanup.build_cleanup_plan",
                        _unsafe_build_cleanup_plan_for_tests):
            code, out = run("remediate-cleanup", "--attempt", r["executed"],
                            "--reason", "historical DryCleanupRunner defect")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["run_validity"], "invalid:harness")
        status = run("status")[1]
        self.assertTrue(status["halted"])
        cell = next(c for c in status["cells"] if c["cell_id"] == r["cell_id"])
        self.assertEqual(cell["state"], "replacement_eligible")


class ResumeSemantics(Base):
    """G10 resume: distinguishing a recoverable operator-review halt from a hard safety halt."""

    GOOD_REPORT = {"commands": [], "executed": True, "cleanup_failed": False,
                   "residue": {"targets": [], "all_clear": True}}

    def _halted_via_real_cleanup_failure(self, s):
        """First execute_next() with a real (non-Dry) cleanup runner that fails -- the forward
        path: correctly classified invalid:harness/replacement_eligible at finalize time, and
        already auto-halted, but NOT yet remediated (no cleanup_remediated event exists yet)."""
        fake = FakeCleanupRunner(ok=False)
        with mock.patch("codeagent_configlab.lifecycle.build_cleanup_plan",
                        _unsafe_build_cleanup_plan_for_tests):
            return s.execute_next(self.runner_factory, self.evaluator_factory, cleanup_runner=fake)

    def test_A_recoverable_halt_blocks_execution_before_resume(self):
        s = self.series()
        s.freeze()
        self._halted_via_real_cleanup_failure(s)
        self.assertTrue(s.halted())
        with self.assertRaises(SeriesStateError):
            s.plan_next()
        with self.assertRaises(SeriesStateError):
            s.execute_next(self.runner_factory, self.evaluator_factory)

    def test_B_C_explicit_resume_clears_halt_but_keeps_history(self):
        s = self.series()
        s.freeze()
        r = self._halted_via_real_cleanup_failure(s)
        halted_before = [e for e in s.events() if e["event"] == "series_halted"]
        self.assertEqual(len(halted_before), 1)
        s.remediate_cleanup(r["executed"], cleanup_report=self.GOOD_REPORT, reason="fixed for real")
        self.assertTrue(s.halted())                                    # remediation alone doesn't resume
        ev = s.resume(reason="operator confirmed remediation")
        self.assertEqual(ev["event"], "series_resumed")
        self.assertFalse(s.halted())                                   # B
        halted_after = [e for e in s.events() if e["event"] == "series_halted"]
        self.assertEqual(halted_after, halted_before)                  # C: byte-identical, untouched

    def test_D_hard_stop_halt_cannot_be_resumed(self):
        s = self.series()
        s.freeze()
        cid = next(iter(s.cells()))
        s._append({"event": "attempt_started", "attempt_id": "synthetic-leak", "cell_id": cid,
                  "kind": "original"})
        s._append({"event": "attempt_finished", "attempt_id": "synthetic-leak", "record": {
            "agent_outcome": "completed", "run_validity": "invalid:leak", "acceptance": "not_run",
            "regression": "not_run", "evaluator_error": False, "c2_protocol": "not_applicable",
            "analysis_eligibility": {"status": "not_countable:invalid", "reason": "invalid:leak"}}})
        s._append({"event": "series_halted", "attempt_id": "synthetic-leak",
                  "reason": "invalid:leak", "category": "hard_stop"})
        self.assertTrue(s.halted())
        with self.assertRaises(SeriesStateError):
            s.resume(reason="trying anyway")
        self.assertTrue(s.halted())

    def test_E_unknown_halt_category_cannot_be_resumed(self):
        s = self.series()
        s.freeze()
        cid = next(iter(s.cells()))
        s._append({"event": "attempt_started", "attempt_id": "synthetic-other", "cell_id": cid,
                  "kind": "original"})
        s._append({"event": "attempt_finished", "attempt_id": "synthetic-other", "record": {
            "agent_outcome": "harness_error", "run_validity": "invalid:harness", "acceptance": "not_run",
            "regression": "not_run", "evaluator_error": False, "c2_protocol": "not_applicable",
            "analysis_eligibility": {"status": "not_countable:invalid", "reason": "invalid:harness"}}})
        # legacy shape (no "category"), and no cleanup_remediated event exists for this attempt
        s._append({"event": "series_halted", "attempt_id": "synthetic-other",
                  "reason": "some unrelated harness problem"})
        self.assertTrue(s.halted())
        with self.assertRaises(SeriesStateError):
            s.resume(reason="trying anyway")

    def test_F_unresolved_residue_cannot_be_resumed(self):
        s = self.series()
        s.freeze()
        r = self._halted_via_real_cleanup_failure(s)
        bad_report = {"commands": [], "executed": True, "cleanup_failed": False,
                     "residue": {"targets": [{"purpose": "x", "target": "/x", "clear": False}],
                                "all_clear": False}}
        s.remediate_cleanup(r["executed"], cleanup_report=bad_report, reason="tried but still dirty")
        with self.assertRaises(SeriesStateError):
            s.resume(reason="trying anyway")
        self.assertTrue(s.halted())

    def test_G_resumable_halt_eventually_reaches_replacement_planning(self):
        s = self.series()
        s.freeze()
        r = self._halted_via_real_cleanup_failure(s)
        s.remediate_cleanup(r["executed"], cleanup_report=self.GOOD_REPORT, reason="fixed")
        s.resume(reason="operator confirms remediation")
        s.approve_replacement(r["cell_id"], "approved after resume")
        # frozen policy: pending originals still come before any approved replacement
        plan = s.plan_next()
        self.assertEqual(plan["next"]["attempt_kind"], "original")
        self.assertNotEqual(plan["next"]["cell_id"], r["cell_id"])
        for _ in range(5):                                              # run out the 5 remaining originals
            out = s.execute_next(self.runner_factory, self.evaluator_factory)
            self.assertEqual(out["kind"], "original")
        plan = s.plan_next()                                            # NOW the replacement is next
        self.assertEqual(plan["next"]["attempt_kind"], "replacement")
        self.assertEqual(plan["next"]["cell_id"], r["cell_id"])
        self.assertEqual(plan["next"]["attempt_ordinal"], 2)
        self.assertTrue(all(e["model"] == MODEL for e in self.agent_log))   # L: no real model call

    def test_H_cell_2_cannot_bypass_while_still_halted(self):
        s = self.series()
        s.freeze()
        self._halted_via_real_cleanup_failure(s)
        self.assertTrue(s.halted())
        pending = [c for c in s.status()["cells"] if c["state"] == "pending"]
        self.assertEqual(len(pending), 5)                                # a real next-pending cell exists
        with self.assertRaises(SeriesStateError):
            s.execute_next(self.runner_factory, self.evaluator_factory)
        self.assertEqual(len([c for c in s.status()["cells"] if c["state"] == "pending"]), 5)

    def test_I_resume_does_not_approve_replacement(self):
        s = self.series()
        s.freeze()
        r = self._halted_via_real_cleanup_failure(s)
        s.remediate_cleanup(r["executed"], cleanup_report=self.GOOD_REPORT, reason="fixed")
        s.resume(reason="ok")
        self.assertEqual(s.cells()[r["cell_id"]].state, "replacement_eligible")
        self.assertFalse(any(e["event"] == "replacement_approved" for e in s.events()))

    def test_J_approval_does_not_execute(self):
        s = self.series()
        s.freeze()
        r = self._halted_via_real_cleanup_failure(s)
        s.remediate_cleanup(r["executed"], cleanup_report=self.GOOD_REPORT, reason="fixed")
        s.resume(reason="ok")
        before = len([e for e in s.events() if e["event"] == "attempt_started"])
        s.approve_replacement(r["cell_id"], "go ahead")
        after = len([e for e in s.events() if e["event"] == "attempt_started"])
        self.assertEqual(before, after)
        self.assertEqual(s.cells()[r["cell_id"]].state, "replacement_approved")

    def test_K_frozen_identities_unchanged_across_resume_and_approval(self):
        s = self.series()
        s.freeze()
        spec_before = json.loads((s.root / "spec.json").read_text())["spec_hash"]
        sched_before = json.loads((s.root / "schedule.json").read_text())
        r = self._halted_via_real_cleanup_failure(s)
        s.remediate_cleanup(r["executed"], cleanup_report=self.GOOD_REPORT, reason="fixed")
        s.resume(reason="ok")
        s.approve_replacement(r["cell_id"], "go")
        spec_after = json.loads((s.root / "spec.json").read_text())["spec_hash"]
        sched_after = json.loads((s.root / "schedule.json").read_text())
        self.assertEqual(spec_before, spec_after)
        self.assertEqual(sched_before, sched_after)

    def test_resume_refuses_when_not_halted(self):
        s = self.series()
        s.freeze()
        with self.assertRaises(SeriesStateError):
            s.resume(reason="nothing to resume")

    def test_legacy_shape_halt_classification_matches_the_real_historical_event(self):
        """Directly mirrors the real pilot-v1 series' actual series_halted event: no "category"
        field (it predates this driver change), reason text
        "cleanup_remediated: historical residue found; operator review required"."""
        s = self.series()
        s.freeze()
        r = self.step(s)                                                # Dry -> historical shape
        s.remediate_cleanup(r["executed"], cleanup_report=self.GOOD_REPORT,
                            reason="historical defect fixed")
        from codeagent_configlab.series import _halt_category

        legacy_halt = {"event": "series_halted", "attempt_id": r["executed"],
                      "reason": "cleanup_remediated: historical residue found; "
                                "operator review required"}
        self.assertEqual(_halt_category(legacy_halt, s.events()), "recoverable")

    def test_legacy_shape_halt_end_to_end_resumable(self):
        s = self.series()
        s.freeze()
        r = self.step(s)                                                # Dry -> historical shape
        s.remediate_cleanup(r["executed"], cleanup_report=self.GOOD_REPORT,
                            reason="historical defect fixed")
        # Test-only fixture edit (never done by the driver itself): strip "category" from the
        # just-appended halt event so its shape exactly matches the real pilot-v1 series' actual
        # historical series_halted event, which predates this field.
        lines = (s.root / "events.jsonl").read_text().splitlines()
        last = json.loads(lines[-1])
        self.assertEqual(last["event"], "series_halted")
        del last["category"]
        lines[-1] = json.dumps(last, sort_keys=True)
        (s.root / "events.jsonl").write_text("\n".join(lines) + "\n")
        self.assertTrue(s.halted())
        ev = s.resume(reason="operator confirms remediation, legacy-shape halt")
        self.assertEqual(ev["event"], "series_resumed")
        self.assertFalse(s.halted())


if __name__ == "__main__":
    unittest.main()
