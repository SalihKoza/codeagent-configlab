"""Package-owned generated-output ignore policy (pilot-readiness cleanup; model-free).

Written as ``unittest`` so it also runs under WSL's stdlib-only Python:

    PYTHONPATH=src:tests python3 -m unittest tests.test_generated_outputs -v
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from _helpers import FakeSandbox, TEST_STATEMENT, make_treated_manifest, make_treatment  # noqa: E402

from codeagent_configlab.agent_state import (  # noqa: E402
    is_generated, take_snapshot, validate_generated_patterns)
from codeagent_configlab.envelope import implementation_envelope  # noqa: E402
from codeagent_configlab.evaluator import SmokeEvaluator  # noqa: E402
from codeagent_configlab.lifecycle import AgentRunOutcome, DryCleanupRunner, RunLifecycle  # noqa: E402
from codeagent_configlab.session import SessionSpec  # noqa: E402
from codeagent_configlab.status import AgentOutcome as AO  # noqa: E402
from codeagent_configlab.task_evaluator import (  # noqa: E402
    CheckSpec, TaskEvaluator, TaskEvaluatorSpec, overlay_candidate)
from codeagent_configlab.task_package import TaskPackage  # noqa: E402

GEN = ("dist/**", "*.tsbuildinfo")
PY = sys.executable


def build_outputs(wc: Path):
    (wc / "dist" / "sub").mkdir(parents=True, exist_ok=True)
    (wc / "dist" / "out.js").write_text("compiled\n")
    (wc / "dist" / "sub" / "more.js").write_text("compiled\n")
    (wc / "tsconfig.tsbuildinfo").write_text("{}\n")


class Agent:
    """Writes generated outputs + real source changes in the implementation phase only
    (optionally in C2 phase 1 too, to prove phase 1 stays strict)."""

    def __init__(self, source_changes=True, write_in_planning=False, edit_claude_md=False):
        self.source_changes, self.write_in_planning = source_changes, write_in_planning
        self.edit_claude_md = edit_claude_md

    def run(self, working_copy, envelope, session, *, prompt=None, deadline=None):
        wc = working_copy.path
        if envelope.phase == "planning" and self.write_in_planning:
            build_outputs(wc)
        if envelope.phase == "implementation":
            build_outputs(wc)
            if self.source_changes:
                (wc / "calc.py").write_text("def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n")
                (wc / "util.py").unlink()
                (wc / "old_name.py").rename(wc / "new_name.py")
            if self.edit_claude_md:
                (wc / "CLAUDE.md").write_text("edited by the agent\n")
        sid = session.session_id
        return AgentRunOutcome(exit_code=0, session_id=sid, agent_outcome=AO.COMPLETED, stdout="ok",
                               events=[{"type": "system", "subtype": "init", "session_id": sid},
                                       {"type": "result", "subtype": "success", "session_id": sid,
                                        "is_error": False, "result": "plan"}])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gen-"))
        self.pristine = self.tmp / "pristine"
        self.pristine.mkdir()
        (self.pristine / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (self.pristine / "util.py").write_text("X = 1\n", encoding="utf-8")
        (self.pristine / "old_name.py").write_text("VALUE = 42\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_life(self, config, agent, generated=GEN):
        home = self.tmp / f"home-{config}"
        (home / ".claude" / "projects").mkdir(parents=True, exist_ok=True)
        life = RunLifecycle(pristine=self.pristine, runs_root=self.tmp / f"runs-{config}",
                            results_root=self.tmp / f"results-{config}", home=home,
                            generated_outputs=generated)
        m = make_treated_manifest(config)
        result = life.execute(manifest=m, envelope=implementation_envelope(config),
                              session=SessionSpec("new", "12345678-1234-4234-8234-123456789abc"),
                              evaluator=SmokeEvaluator(), agent_runner=agent,
                              cleanup_runner=DryCleanupRunner(), treatment=make_treatment(config),
                              task_statement=TEST_STATEMENT)
        run_dir = self.tmp / f"results-{config}" / m.run_id
        load = lambda n: json.loads((run_dir / n).read_text(encoding="utf-8"))  # noqa: E731
        return result, run_dir, load


class Patterns(unittest.TestCase):
    def test_matcher(self):
        self.assertTrue(is_generated("dist/a.js", GEN))
        self.assertTrue(is_generated("dist/x/b.js", GEN))
        self.assertTrue(is_generated("tsconfig.tsbuildinfo", GEN))
        self.assertTrue(is_generated("pkg/tsconfig.tsbuildinfo", GEN))
        for rel in ("src/dist/a.ts", "distx/a", "dist", "src/index.ts", "package.json",
                    "tsconfig.json", "CLAUDE.md", ".claude/x.tsbuildinfo", "sub/CLAUDE.md"):
            self.assertFalse(is_generated(rel, GEN), rel)
        self.assertFalse(is_generated("dist/a.js", ()))

    def test_dangerous_patterns_rejected(self):
        self.assertEqual(validate_generated_patterns(["dist/**", "*.tsbuildinfo", "build/**",
                                                      "coverage/**", "*.pyc"]), [])
        for bad in ("src/**", "tests/**", "test/**", "lib/**", "node_modules/**", "**", "*",
                    "*.ts", "*.d.ts", "*.js", "*.json", "*.py", "*.md", "package.json",
                    "tsconfig.json", "CLAUDE.md", ".claude/**", ".git/**", "../x/**", "/x/**",
                    "a/b/**", "dist", "*.", "dist/*", "d*st/**"):
            self.assertTrue(validate_generated_patterns([bad]), bad)


class Capture(Base):
    def test_generated_ignored_but_source_changes_visible(self):
        result, run_dir, load = self.run_life("C0", Agent())
        cf = load("changed_files.json")
        self.assertEqual(cf["modified"], ["calc.py"])
        self.assertEqual(cf["deleted"], ["util.py"])
        self.assertEqual(cf["renamed"], [["old_name.py", "new_name.py"]])
        flat = json.dumps(cf)
        self.assertNotIn("dist/", flat)
        self.assertNotIn("tsbuildinfo", flat)
        diff = (run_dir / "final.diff").read_text()
        self.assertIn("calc.py", diff)
        self.assertNotIn("dist/", diff)
        self.assertNotIn("tsbuildinfo", diff)
        fs = load("final_state.json")
        self.assertEqual(fs["generated_ignore"], list(GEN))
        self.assertFalse(any(k.startswith("dist/") for k in fs["files"]))
        self.assertEqual(load("start_state.json")["generated_ignore"], list(GEN))
        # without a policy the same outputs WOULD show up (the policy is what hides them)
        _, _, load2 = self.run_life("C1", Agent(), generated=())
        self.assertIn("dist/out.js", load2("changed_files.json")["added"])

    def test_treatment_drift_still_detected(self):
        result, _, load = self.run_life("C1", Agent(source_changes=False, edit_claude_md=True))
        self.assertEqual(result.run_validity.value, "invalid:treatment_drift")
        self.assertIn("CLAUDE.md", load("changed_files.json")["modified"])

    def test_same_policy_for_c0_c1_c2(self):
        seen = {}
        for config in ("C0", "C1", "C2"):
            result, _, load = self.run_life(config, Agent())
            self.assertEqual(result.run_validity.value, "valid", config)
            cf = load("changed_files.json")
            seen[config] = (tuple(load("final_state.json")["generated_ignore"]),
                            tuple(cf["modified"]), tuple(cf["deleted"]),
                            tuple(map(tuple, cf["renamed"])),
                            tuple(a for a in cf["added"] if a != "CLAUDE.md"))
        self.assertEqual(len(set(seen.values())), 1, seen)

    def test_c2_phase1_stays_strict(self):
        result, _, load = self.run_life("C2", Agent(write_in_planning=True))
        self.assertEqual(result.c2_protocol.value, "phase1_write")
        self.assertEqual(result.run_validity.value, "invalid:c2_protocol")

    def test_invalid_policy_refused_by_lifecycle(self):
        with self.assertRaises(ValueError):
            self.run_life("C0", Agent(), generated=("src/**",))


class EvaluatorCopy(Base):
    def test_generated_outputs_never_reach_a_check(self):
        cand = overlay_candidate(self.pristine, None, self.tmp / "cand")
        build_outputs(cand)
        (cand / "dist" / "evil.js").write_text("module.exports = 'pass anyway'\n")
        check = CheckSpec("no-dist", (PY, "-c", "import os, sys; sys.exit(1 if os.path.exists('dist/evil.js') "
                                                "or os.path.exists('tsconfig.tsbuildinfo') else 0)"), 30)
        spec = TaskEvaluatorSpec(pristine=self.pristine, acceptance=(check,),
                                 regression=(CheckSpec("ok", (PY, "-c", "pass"), 30),),
                                 generated_outputs=GEN)
        before = take_snapshot(cand).tree_hash
        r = TaskEvaluator(spec, sandbox=FakeSandbox()).evaluate(cand)
        self.assertEqual(r.acceptance.value, "pass", r.checks)
        removed = {x["path"] for x in r.restoration if x["action"] == "generated_removed"}
        self.assertTrue({"dist/evil.js", "dist/out.js", "tsconfig.tsbuildinfo"} <= removed)
        self.assertEqual(take_snapshot(cand).tree_hash, before)        # canonical copy untouched
        with self.assertRaises(ValueError):
            TaskEvaluatorSpec(pristine=self.pristine, acceptance=(check,), regression=(check,),
                              generated_outputs=("tests/**",))


class Identity(Base):
    def make_pkg(self, generated):
        from test_series import make_package

        pkg = make_package(self.tmp / "packages", "P-SYN-A")
        meta = json.loads((pkg / "package.json").read_text())
        meta["generated_outputs"] = list(generated)
        (pkg / "package.json").write_text(json.dumps(meta))
        meta["validity_gate"]["task_version_hash"] = TaskPackage.load(pkg).version_hash()
        (pkg / "package.json").write_text(json.dumps(meta))
        return pkg, meta

    def test_policy_is_part_of_task_identity_and_frozen_spec(self):
        from codeagent_configlab.series import Series, SeriesConfig, SeriesFrozenError

        pkg, meta = self.make_pkg(GEN)
        p = TaskPackage.load(pkg)
        self.assertEqual(p.gate_errors(), [])
        self.assertEqual(p.evaluator_spec().generated_outputs, GEN)
        v1 = p.version_hash()
        s = Series(root=self.tmp / "series", harness_root=self.tmp, home=self.tmp / "h",
                   config=SeriesConfig(pilot_version="p", package_dirs=[str(pkg)]))
        s.freeze()
        # change only the ignore policy (and even re-gate it): identity changes, frozen spec fails
        meta["generated_outputs"] = ["dist/**"]
        (pkg / "package.json").write_text(json.dumps(meta))
        self.assertNotEqual(TaskPackage.load(pkg).version_hash(), v1)
        self.assertTrue(TaskPackage.load(pkg).gate_errors())
        meta["validity_gate"]["task_version_hash"] = TaskPackage.load(pkg).version_hash()
        (pkg / "package.json").write_text(json.dumps(meta))
        with self.assertRaises(SeriesFrozenError):
            s.verify_frozen(require_ready=False)

    def test_invalid_or_preshipped_generated_outputs_rejected(self):
        pkg, meta = self.make_pkg(GEN)
        meta["generated_outputs"] = ["src/**"]
        (pkg / "package.json").write_text(json.dumps(meta))
        with self.assertRaises(ValueError):
            TaskPackage.load(pkg)
        shutil.rmtree(self.tmp / "packages")
        pkg, meta = self.make_pkg(GEN)
        (pkg / "pristine" / "dist").mkdir()
        (pkg / "pristine" / "dist" / "shipped.js").write_text("x\n")
        meta["validity_gate"]["task_version_hash"] = TaskPackage.load(pkg).version_hash()
        (pkg / "package.json").write_text(json.dumps(meta))
        errs = TaskPackage.load(pkg).gate_errors()
        self.assertTrue(any("already contains declared generated outputs" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
