"""Frozen pilot treatment texts (operator-approved 2026-09-28) -- byte/hash/content checks.

Written as ``unittest`` so it also runs under WSL's stdlib-only Python:

    PYTHONPATH=src:tests python3 -m unittest tests.test_treatment_candidates -v

Model-free. The three hashes are pinned here as literals *and* in ``treatments/pilot-v1/FREEZE.json``:
a byte change fails even if the JSON is edited alongside it. Changing a frozen text requires a new
pilot version, not an edit here.
"""

import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "src"))

from codeagent_configlab.series import DEFAULT_ORDER_SEED_TEXT  # noqa: E402
from codeagent_configlab.treatment import TASK_STATEMENT_SLOT, Treatment  # noqa: E402

D = REPO / "treatments" / "pilot-v1"
CAND = json.loads((D / "FREEZE.json").read_text(encoding="utf-8"))
FROZEN_SHA256 = {   # operator-approved 2026-09-28 (CLAUDE.md confirmed as the full 64-hex value)
    "claude_md": "213df66805a816a4dea6998580fd85c91c3d3a1beb08acb3dbdf7ddc000e0541",
    "planning_wrapper": "299b08446b440345a7f177258208c3bf8b1d33addc3934ed1356bb72a0c47fc4",
    "approval_message": "dbf445a514ca2ae9576935d09d7add9cf9157f88ca01ae1388d65a1f1009ee14",
}
FILES = {k: REPO / v["path"] for k, v in CAND["treatment"].items()}

FORBIDDEN = (
    # task identity / solution domain of the pilot tasks
    "p-py", "p-ts", "rangefmt", "collapse_ranges", "normaliz", "exporter", "range",
    # experiment internals
    "hidden", "evaluator", "reference solution", "benchmark", "pilot", "experiment", "score",
    "grade", "c0", "c1", "c2", "configuration",
    # language / tool specific content (belongs in each fixture's README)
    "python", "typescript", "javascript", "pytest", "unittest", "npm", "node", "tsc", "dist/",
)


def treatment():
    return Treatment.from_files(FILES["claude_md"], FILES["planning_wrapper"], FILES["approval_message"])


class Bytes(unittest.TestCase):
    def test_hashes_are_reproducible_from_exact_bytes(self):
        t = treatment()
        got = {"claude_md": t.claude_md_hash, "planning_wrapper": t.planning_wrapper_hash,
               "approval_message": t.approval_message_hash}
        for key, path in FILES.items():
            data = path.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), FROZEN_SHA256[key], key)
            self.assertEqual(CAND["treatment"][key]["sha256"], FROZEN_SHA256[key], key)
            self.assertEqual(len(data), CAND["treatment"][key]["bytes"], key)
            self.assertEqual(got[key], CAND["treatment"][key]["sha256"], key)   # as the harness hashes

    def test_encoding_and_newlines(self):
        for key, path in FILES.items():
            data = path.read_bytes()
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"), key)
            self.assertNotIn(b"\r", data, key)
            self.assertTrue(data.endswith(b"\n") and not data.endswith(b"\n\n"), key)
            data.decode("utf-8")

    def test_status_frozen_treatment_and_frozen_execution_parameters(self):
        self.assertEqual(CAND["status"], "FROZEN")
        self.assertEqual(CAND["order_seed_status"], "FROZEN")
        self.assertFalse((D / "FREEZE_CANDIDATE.json").exists())
        # Execution-spec parameters (2026-09-29 operator freeze), not the treatment bytes/seed.
        self.assertEqual(CAND["model_request"], "claude-sonnet-5")
        self.assertNotEqual(CAND["model_request"], "Default")
        self.assertEqual(CAND["effort_request"], "high")
        self.assertEqual(CAND["timeout_seconds"], 900)


class Content(unittest.TestCase):
    def test_no_task_or_experiment_specific_content(self):
        for key, path in FILES.items():
            text = path.read_text(encoding="utf-8").lower()
            for term in FORBIDDEN:
                self.assertIsNone(re.search(r"(?<![a-z])" + re.escape(term), text), (key, term))

    def test_wrapper_embeds_the_statement_unmodified_once(self):
        t = treatment()
        self.assertEqual(t.planning_wrapper.count(TASK_STATEMENT_SLOT), 1)
        self.assertEqual(t.planning_wrapper.count("{{"), 1)
        stmt = "Line one of an arbitrary statement.\n\n  indented `code` and {braces}\n"
        rendered = t.render_planning_prompt(stmt)
        self.assertIn(stmt, rendered)
        self.assertEqual(rendered.replace(stmt, TASK_STATEMENT_SLOT), t.planning_wrapper)

    def test_approval_is_fixed_and_content_free(self):
        a = treatment().approval_message
        self.assertNotIn("{", a)
        self.assertEqual(a.count("\n"), 1)                                  # one short line
        self.assertLess(len(a), 160)

    def test_claude_md_is_short_and_generic(self):
        md = FILES["claude_md"].read_text(encoding="utf-8")
        self.assertLessEqual(len(md.splitlines()), 12)
        # public test files are protected paths: the file must not push agents into editing them
        for phrase in ("add test", "add a test", "write test", "update test", "new test",
                       "modify test", "update the test", "add or update"):
            self.assertNotIn(phrase, md.lower())


class HarnessIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="treat-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_c0_c1_c2_relationship_and_readiness(self):
        from test_series import make_package

        from codeagent_configlab.series import (Series, SeriesConfig, build_spec, generate_schedule,
                                                readiness_errors)

        pkgs = [make_package(self.tmp / "p", "P-SYN-A"), make_package(self.tmp / "p", "P-SYN-B")]
        cfg = SeriesConfig(pilot_version="pilot-v1", package_dirs=[str(p) for p in pkgs],
                           claude_md_file=str(FILES["claude_md"]),
                           planning_wrapper_file=str(FILES["planning_wrapper"]),
                           approval_message_file=str(FILES["approval_message"]))
        spec = build_spec(cfg)
        self.assertEqual(spec["treatment"], {
            "claude_md_hash": CAND["treatment"]["claude_md"]["sha256"],
            "planning_wrapper_hash": CAND["treatment"]["planning_wrapper"]["sha256"],
            "approval_message_hash": CAND["treatment"]["approval_message"]["sha256"]})
        # only the operator values remain OPEN once these texts are supplied (this local
        # SeriesConfig doesn't read FREEZE.json's frozen model/effort/timeout, only the treatment
        # file paths, so it still exercises the fully-OPEN readiness path)
        self.assertEqual(sorted(readiness_errors(spec)),
                         sorted(["model_request is OPEN", "effort_request is OPEN",
                                 "timeout_seconds is not frozen ('OPEN')"]))
        sched = generate_schedule(spec)
        s = Series(root=self.tmp / "s", config=cfg, harness_root=self.tmp, home=self.tmp / "h")
        by_cfg = {c["configuration"]: s.build_manifest(spec, sched, c, kind="original", ordinal=1)
                  for c in sched["cells"] if c["task_id"] == "P-SYN-A"}
        c0, c1, c2 = by_cfg["C0"], by_cfg["C1"], by_cfg["C2"]
        self.assertIsNone(c0.claude_md_hash)
        self.assertEqual(c1.claude_md_hash, c2.claude_md_hash)
        self.assertEqual(c1.claude_md_hash, CAND["treatment"]["claude_md"]["sha256"])
        self.assertIsNone(c1.planning_wrapper_hash)
        self.assertIsNone(c1.approval_message_hash)
        self.assertEqual(c2.planning_wrapper_hash, CAND["treatment"]["planning_wrapper"]["sha256"])
        self.assertEqual(c2.approval_message_hash, CAND["treatment"]["approval_message"]["sha256"])
        self.assertEqual(c0.settings_policy_hash, c1.settings_policy_hash)
        self.assertEqual(c1.settings_policy_hash, c2.settings_policy_hash)   # same impl envelope


class Seed(unittest.TestCase):
    def test_seed_text_is_the_documented_default(self):
        self.assertEqual(CAND["order_seed_text"], "configlab-pilot-v1-order")
        self.assertEqual(CAND["order_seed_text"], DEFAULT_ORDER_SEED_TEXT)
        plan = (REPO / "docs" / "PILOT_PLAN.md").read_text(encoding="utf-8")
        self.assertIn('sha256(b"configlab-pilot-v1-order")', plan)
        self.assertEqual(CAND["order_seed_int"],
                         int(hashlib.sha256(b"configlab-pilot-v1-order").hexdigest()[:8], 16))


if __name__ == "__main__":
    unittest.main()
