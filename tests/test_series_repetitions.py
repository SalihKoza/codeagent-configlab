"""Gate 2: FINAL-namespace repetitions and the protocol §11 blocked schedule (model-free).

Written as ``unittest`` so it also runs under WSL's stdlib-only Python:

    PYTHONPATH=src:tests python3 -m unittest tests.test_series_repetitions -v

Covers: exact reproduction of the frozen pilot-v1 identities from the in-repo inputs; a 54-cell
FINAL series (6 synthetic placeholder tasks x C0/C1/C2 x 3 repetitions); determinism; seed
sensitivity; resume/plan/replacement semantics with repetitions; invalid repetition values; the
model-free CLI freeze/plan/status path. No Claude call, no srt, never ``run-next --execute``.
"""

import contextlib
import hashlib
import io
import json
import os
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import test_series as ts  # noqa: E402  (helpers only; no test classes are re-collected)
from _helpers import TEST_APPROVAL, TEST_CLAUDE_MD, TEST_WRAPPER  # noqa: E402

from codeagent_configlab.series import (  # noqa: E402
    CONFIGURATIONS, FINAL_ORDER_RULE, Series, SeriesConfig, SeriesError, SeriesFrozenError,
    _validate, build_spec, final_block_seed, generate_schedule, readiness_errors)
from codeagent_configlab.status import AgentOutcome as AO  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

# Frozen pilot-v1 identities (docs/PILOT_V1_CLOSEOUT.md §2-§3).
PILOT_SPEC_HASH = "90628ef77d385c98ed5ee8ec1f7c6e9a709da91c6cb11c2cdff5ccb0736b4b81"
PILOT_SCHEDULE_HASH = "ebd175cddd622153138323d8116a06e001650f96960cf03bd16de1a5bd04bfe9"
PILOT_CELLS = [
    (1, "cell-fe764020303430fd", "P-TS-01", "C0"),
    (2, "cell-be645426fc613334", "P-PY-01", "C1"),
    (3, "cell-e5edb916959ba3d7", "P-TS-01", "C2"),
    (4, "cell-af7114946671407f", "P-PY-01", "C2"),
    (5, "cell-c2708598bbb89ec1", "P-TS-01", "C1"),
    (6, "cell-7bb8b30547dbb18c", "P-PY-01", "C0"),
]
FINAL_TASKS = [f"F-SYN-{i}" for i in range(1, 7)]

_COUNTABLE_RECORD = {"agent_outcome": "completed", "run_validity": "valid", "acceptance": "pass",
                     "regression": "pass", "evaluator_error": False, "c2_protocol": None,
                     "analysis_eligibility": {"status": "countable",
                                              "reason": "valid_outcome:completed"},
                     "invalid_reason": None}


def pilot_config() -> SeriesConfig:
    """The pilot-v1 series inputs, from the repository (values: treatments/pilot-v1/FREEZE.json)."""
    tr = REPO / "treatments" / "pilot-v1"
    return SeriesConfig(
        pilot_version="pilot-v1",
        package_dirs=[str(REPO / "fixtures" / "pilot" / "P-PY-01"),
                      str(REPO / "fixtures" / "pilot" / "P-TS-01")],
        model_request="claude-sonnet-5", effort_request="high", timeout_seconds=900,
        claude_md_file=str(tr / "claude_md.md"),
        planning_wrapper_file=str(tr / "planning_wrapper.txt"),
        approval_message_file=str(tr / "approval_message.txt"),
        order_seed_text="configlab-pilot-v1-order")


def _byte_preserving_checkout() -> bool:
    return os.path.islink(REPO / "fixtures" / "pilot" / "P-TS-01" / "pristine" / "node_modules"
                          / ".bin" / "tsc")


@unittest.skipUnless(_byte_preserving_checkout(),
                     "P-TS-01 node_modules/.bin symlinks are not real symlinks here (README: "
                     "non-byte-preserving checkout); pilot identity cannot be checked")
class A_PilotReproduction(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g2-pilot-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exact_spec_schedule_and_cells(self):
        spec = build_spec(pilot_config())
        self.assertEqual(spec["spec_hash"], PILOT_SPEC_HASH)
        self.assertNotIn("order_rule", spec)                         # no new serialized fields
        sched = generate_schedule(spec)
        self.assertEqual(sched["schedule_hash"], PILOT_SCHEDULE_HASH)
        self.assertEqual([(c["position"], c["cell_id"], c["task_id"], c["configuration"])
                          for c in sched["cells"]], PILOT_CELLS)
        self.assertTrue(all(c["repetition"] == 1 for c in sched["cells"]))
        self.assertEqual(set(sched), {"schema", "pilot_version", "spec_hash", "order_seed_text",
                                      "seed", "cells", "schedule_hash"})
        self.assertEqual(readiness_errors(spec), [])

    def test_freeze_and_verify_round_trip(self):
        s = Series(root=self.tmp / "series" / "pilot-v1", config=pilot_config(),
                   harness_root=self.tmp, home=self.tmp / "home")
        out = s.freeze()
        self.assertEqual((out["spec_hash"], out["schedule_hash"]),
                         (PILOT_SPEC_HASH, PILOT_SCHEDULE_HASH))
        spec, sched = s.verify_frozen(require_ready=True)
        self.assertEqual(sched["schedule_hash"], PILOT_SCHEDULE_HASH)
        self.assertEqual(s.plan_next()["next"]["cell_id"], PILOT_CELLS[0][1])


class FinalBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g2-final-"))
        self.harness = self.tmp / "harness"
        pk = self.harness / "packages"
        self.pkgs = [ts.make_package(pk, tid) for tid in FINAL_TASKS]
        tr = self.harness / "treatments"
        tr.mkdir(parents=True)
        (tr / "CLAUDE.md").write_bytes(TEST_CLAUDE_MD)
        (tr / "wrapper.txt").write_text(TEST_WRAPPER, encoding="utf-8")
        (tr / "approval.txt").write_text(TEST_APPROVAL, encoding="utf-8")
        self.home = self.tmp / "home"
        (self.home / ".claude" / "projects").mkdir(parents=True)
        self.plan, self.agent_log = {}, []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def config(self, **over):
        tr = self.harness / "treatments"
        base = dict(pilot_version="final-test", package_dirs=[str(p) for p in self.pkgs],
                    model_request=ts.MODEL, effort_request=ts.EFFORT, timeout_seconds=600,
                    claude_md_file=str(tr / "CLAUDE.md"), planning_wrapper_file=str(tr / "wrapper.txt"),
                    approval_message_file=str(tr / "approval.txt"),
                    order_seed_text="synthetic-final-seed", repetitions=3, namespace="FINAL")
        base.update(over)
        return SeriesConfig(**base)

    def series(self, config=None, name="final-test") -> Series:
        return Series(root=self.harness / "series" / name, config=config or self.config(),
                      harness_root=self.harness, home=self.home)

    def runner_factory(self, manifest):
        return ts.ScriptedAgent(manifest, self.plan, self.agent_log)

    def evaluator_factory(self, pkg):
        return ts.fake_evaluator_for(None, pkg)

    def step(self, s):
        return s.execute_next(self.runner_factory, self.evaluator_factory)


class B_FinalConstruction(FinalBase):
    def test_54_cells_three_complete_blocks(self):
        spec = build_spec(self.config())
        self.assertEqual((spec["namespace"], spec["repetitions"]), ("FINAL", 3))
        self.assertEqual(_validate(spec, "pilot-series-spec.schema.json"), [])
        self.assertEqual(readiness_errors(spec), [])
        sched = generate_schedule(spec)
        cells = sched["cells"]
        self.assertEqual(len(cells), 54)
        self.assertEqual([c["position"] for c in cells], list(range(1, 55)))
        pairs = {(t, c) for t in FINAL_TASKS for c in CONFIGURATIONS}
        for rep in (1, 2, 3):
            block = cells[(rep - 1) * 18: rep * 18]                  # blocks contiguous, 1 -> 3
            self.assertTrue(all(c["repetition"] == rep for c in block))
            self.assertEqual(len(block), 18)
            self.assertEqual({(c["task_id"], c["configuration"]) for c in block}, pairs)
        tuples = [(c["task_id"], c["configuration"], c["repetition"]) for c in cells]
        self.assertEqual(len(set(tuples)), 54)
        self.assertEqual(set(tuples), {(t, c, r) for (t, c) in pairs for r in (1, 2, 3)})
        self.assertEqual(len({c["cell_id"] for c in cells}), 54)
        self.assertEqual(sched["order_rule"], FINAL_ORDER_RULE)
        self.assertNotIn("seed", sched)

    def test_documented_per_block_derivation(self):
        spec = build_spec(self.config())
        sched = generate_schedule(spec)
        canonical = [(t, c) for t in sorted(FINAL_TASKS) for c in ("C0", "C1", "C2")]
        expected, seeds = [], []
        for rep in (1, 2, 3):
            seed = int(hashlib.sha256(f"synthetic-final-seed#block-{rep}".encode()).hexdigest()[:8], 16)
            self.assertEqual(final_block_seed("synthetic-final-seed", rep), seed)
            seeds.append(seed)
            perm = list(canonical)
            random.Random(seed).shuffle(perm)
            expected += [(t, c, rep) for t, c in perm]
        self.assertEqual(sched["block_seeds"], seeds)
        self.assertEqual([(c["task_id"], c["configuration"], c["repetition"])
                          for c in sched["cells"]], expected)

    def test_repetition_is_part_of_cell_identity(self):
        cells = generate_schedule(build_spec(self.config()))["cells"]
        by_pair = {}
        for c in cells:
            by_pair.setdefault((c["task_id"], c["configuration"]), set()).add(c["cell_id"])
        self.assertTrue(all(len(ids) == 3 for ids in by_pair.values()))


class C_Determinism(FinalBase):
    def test_same_spec_same_schedule(self):
        a = generate_schedule(build_spec(self.config()))
        b = generate_schedule(build_spec(self.config()))
        self.assertEqual(a, b)
        self.assertEqual(a["schedule_hash"], b["schedule_hash"])

    def test_two_independent_freezes_agree(self):
        s1, s2 = self.series(name="one"), self.series(name="two")
        f1, f2 = s1.freeze(), s2.freeze()
        self.assertEqual((f1["spec_hash"], f1["schedule_hash"]), (f2["spec_hash"], f2["schedule_hash"]))
        self.assertEqual(s1.frozen()[1]["cells"], s2.frozen()[1]["cells"])
        self.assertTrue(s1.freeze()["already_frozen"])


class D_SeedSensitivity(FinalBase):
    def test_seed_controls_order_not_cell_set(self):
        orders, sets, block_orders = set(), set(), set()
        for i in range(8):
            cells = generate_schedule(build_spec(self.config(order_seed_text=f"seed-{i}")))["cells"]
            orders.add(tuple(c["cell_id"] for c in cells))
            sets.add(frozenset((c["task_id"], c["configuration"], c["repetition"]) for c in cells))
            for rep in (1, 2, 3):
                block_orders.add(tuple((c["task_id"], c["configuration"])
                                       for c in cells if c["repetition"] == rep))
        self.assertEqual(len(sets), 1)                               # same planned cells
        self.assertGreater(len(orders), 1)                           # seed changes order
        self.assertGreater(len(block_orders), 1)                     # blocks get own permutations


class E_ResumeAndReplacement(FinalBase):
    def test_plan_resume_and_replacement_with_repetitions(self):
        s = self.series()
        s.freeze()
        sched = s.frozen()[1]
        first = s.plan_next()["next"]
        self.assertEqual((first["position"], first["repetition"], first["attempt_kind"],
                          first["attempt_ordinal"]), (1, 1, "original", 1))
        c1 = sched["cells"][0]
        self.plan[(c1["task_id"], c1["configuration"], 1)] = (AO.LIMIT_INTERRUPTED, False)
        r1 = self.step(s)
        r2 = self.step(s)
        self.assertEqual(r1["decision"], "eligible")
        self.assertEqual(r2["decision"], "complete")
        m1 = json.loads((s.attempts_root / r1["executed"] / "manifest.json").read_text())
        self.assertEqual((m1["namespace"], m1["repetition"], m1["attempt_kind"], m1["cell_id"]),
                         ("FINAL", 1, "original", c1["cell_id"]))

        s2 = self.series()                                           # fresh process view
        self.assertEqual(s2.plan_next()["next"]["position"], 3)
        s2.approve_replacement(c1["cell_id"], reason="subscription limit (test)")
        nxt = s2.plan_next()["next"]
        self.assertEqual((nxt["position"], nxt["attempt_kind"]), (3, "original"))   # originals first

        # State-only: mark the remaining 52 originals countable (no agent, no lifecycle).
        for c in sched["cells"][2:]:
            aid = f"run_synthetic_{c['position']:02d}"
            s2._append({"event": "attempt_started", "attempt_id": aid, "cell_id": c["cell_id"],
                        "position": c["position"], "ordinal": 1, "kind": "original"})
            s2._append({"event": "attempt_finished", "attempt_id": aid, "record": _COUNTABLE_RECORD})
        nxt = s2.plan_next()["next"]
        self.assertEqual((nxt["cell_id"], nxt["attempt_kind"], nxt["attempt_ordinal"], nxt["repetition"]),
                         (c1["cell_id"], "replacement", 2, 1))
        r3 = self.step(s2)                                           # frozen_cell_spec_hash checked inside
        self.assertEqual(r3["kind"], "replacement")
        m3 = json.loads((s2.attempts_root / r3["executed"] / "manifest.json").read_text())
        self.assertEqual((m3["repetition"], m3["cell_id"], m3["original_attempt_id"]),
                         (1, c1["cell_id"], r1["executed"]))
        status = s2.status()
        self.assertEqual(len(status["cells"]), 54)                    # planned cells unchanged
        self.assertEqual(sum(len(c["attempts"]) for c in status["cells"]), 55)
        self.assertEqual({c["state"] for c in status["cells"]}, {"observed"})
        self.assertEqual(sorted({c["repetition"] for c in status["cells"]}), [1, 2, 3])
        self.assertTrue(self.step(s2)["done"])

    def test_resume_revalidates_frozen_schedule(self):
        s = self.series()
        s.freeze()
        s.verify_frozen(require_ready=True)
        path = s.root / "schedule.json"
        data = json.loads(path.read_text())
        data["cells"][0], data["cells"][1] = data["cells"][1], data["cells"][0]
        path.write_text(json.dumps(data))
        with self.assertRaises(SeriesFrozenError):
            s.verify_frozen(require_ready=False)

    def test_crash_detection_with_repetitions(self):
        s = self.series()
        s.freeze()
        r = self.step(s)
        lines = (s.root / "events.jsonl").read_text().splitlines()
        (s.root / "events.jsonl").write_text("\n".join(lines[:-1]) + "\n")
        self.assertEqual(s.cells()[r["cell_id"]].state, "ambiguous")
        self.assertTrue(s.recover(r["executed"])["recovered"])
        self.assertEqual(s.cells()[r["cell_id"]].state, "observed")


class F_InvalidValues(FinalBase):
    def test_non_positive_or_non_integer_repetitions_rejected(self):
        for bad in (0, -1, True, 1.5, "3", None):
            with self.subTest(bad=bad), self.assertRaises(SeriesError):
                build_spec(self.config(repetitions=bad))

    def test_readiness_rejects_tampered_repetitions(self):
        spec = build_spec(self.config())
        for bad in (0, -2):
            self.assertTrue(any("repetitions" in e for e in readiness_errors({**spec, "repetitions": bad})))

    def test_pilot_namespace_keeps_one_repetition(self):
        cfg = self.config(namespace="PILOT", repetitions=3,
                          package_dirs=[str(ts.make_package(self.tmp / "p", "P-SYN-A"))])
        spec = build_spec(cfg)
        self.assertTrue(any("PILOT" in e for e in readiness_errors(spec)))
        with self.assertRaises(SeriesError):
            generate_schedule(spec)
        with self.assertRaises(SeriesError):
            self.series(config=cfg, name="pilot-reps").freeze()

    def test_final_refuses_pilot_tasks_and_other_namespaces(self):
        pilot_pkg = ts.make_package(self.tmp / "p", "P-SYN-A")
        with self.assertRaisesRegex(SeriesError, r"pilot task P-SYN-A .*FINAL.*F16"):
            build_spec(self.config(package_dirs=[str(self.pkgs[0]), str(pilot_pkg)]))
        with self.assertRaisesRegex(SeriesError, "namespaces"):
            build_spec(self.config(namespace="HARNESS_SMOKE_ONLY"))
        spec = build_spec(self.config())
        self.assertTrue(_validate({**spec, "namespace": "HARNESS_SMOKE_ONLY"},
                                  "pilot-series-spec.schema.json"))


class G_CliDryFinalSeries(FinalBase):
    def test_freeze_plan_status_model_free(self):
        from codeagent_configlab.__main__ import main

        cfg = self.config()
        path = self.tmp / "series.json"
        path.write_text(json.dumps({
            "pilot_version": cfg.pilot_version, "namespace": "FINAL", "repetitions": 3,
            "package_dirs": cfg.package_dirs, "order_seed_text": cfg.order_seed_text,
            "claude_md_file": cfg.claude_md_file, "planning_wrapper_file": cfg.planning_wrapper_file,
            "approval_message_file": cfg.approval_message_file}))       # model/effort/timeout OPEN
        common = ["--config", str(path), "--harness-root", str(self.harness), "--home", str(self.home)]

        def run(*a):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["series", *a, *common])
            return code, json.loads(buf.getvalue())

        code, frozen = run("freeze")
        self.assertEqual(code, 0)
        code, plan = run("plan")
        self.assertEqual(code, 0)
        self.assertEqual((plan["next"]["position"], plan["next"]["repetition"]), (1, 1))
        self.assertTrue(plan["readiness_errors"])                     # OPEN values: not executable
        code, status = run("status")
        self.assertEqual(code, 0)
        self.assertEqual(status["schedule_hash"], frozen["schedule_hash"])
        self.assertEqual(len(status["cells"]), 54)
        self.assertEqual({c["state"] for c in status["cells"]}, {"pending"})
        self.assertEqual(run("run-next")[0], 2)                      # refuses without --execute
        root = self.harness / "series" / "final-test"
        spec = json.loads((root / "spec.json").read_text())
        self.assertEqual(spec["namespace"], "FINAL")
        self.assertFalse((root / "attempts").exists())
        self.assertFalse((root / "events.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
