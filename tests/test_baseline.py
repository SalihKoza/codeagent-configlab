"""G6: deterministic neutral git baseline, identical for C0/C1/C2, free of hidden/reference material."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from _helpers import TEST_STATEMENT, make_treated_manifest, make_treatment

from codeagent_configlab import baseline as bl
from codeagent_configlab.envelope import implementation_envelope
from codeagent_configlab.evaluator import SmokeEvaluator
from codeagent_configlab.lifecycle import AgentRunOutcome, DryCleanupRunner, RunLifecycle
from codeagent_configlab.session import SessionSpec
from codeagent_configlab.status import AgentOutcome, RunValidity
from codeagent_configlab.workspace import make_working_copy

UUID = "12121212-3434-5656-7878-909090909090"
REF_MARKER = "REFERENCE-SOLUTION-MARKER-9f1c"
HIDDEN_MARKER = "HIDDEN-TEST-MARKER-77ab"


def git(repo, *args) -> str:
    """Test-side git on trusted test repositories only."""
    out = subprocess.run(["git", *args], cwd=str(repo), env=bl._git_env(),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return out.stdout.decode("utf-8", "replace")


def _task_layout(tmp_path):
    """harness-like layout: pristine fixture next to (never inside) reference and hidden material."""
    task = tmp_path / "harness" / "tasks" / "P-TEST"
    pristine = task / "pristine"
    (pristine / "pkg").mkdir(parents=True)
    (pristine / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (pristine / "pkg" / "util.py").write_text("X = 1\n", encoding="utf-8")
    (task / "reference").mkdir()
    (task / "reference" / "calc.py").write_text(f"# {REF_MARKER}\ndef multiply(a, b): return a * b\n")
    (task / "hidden").mkdir()
    (task / "hidden" / "check.py").write_text(f"# {HIDDEN_MARKER}\n")
    return pristine


def test_a_baseline_commit_is_deterministic(tmp_path):
    pristine = _task_layout(tmp_path)
    ids = set()
    for i in range(3):
        wc = make_working_copy(pristine, tmp_path / f"runs{i}", seed_settings=True, git_baseline=True)
        ids.add(wc.baseline_commit)
        assert git(wc.path, "rev-list", "--count", "HEAD").strip() == "1"
        assert bl.read_head(wc.path) == wc.baseline_commit
    assert len(ids) == 1
    assert ids == {bl.expected_baseline_commit(pristine)}
    log = git(wc.path, "log", "--format=%an <%ae>|%ad|%s", "--date=raw")
    assert log.strip() == "Developer <dev@example.invalid>|946684800 +0000|Initial commit"


def test_seeds_are_not_part_of_the_baseline(tmp_path):
    wc = make_working_copy(_task_layout(tmp_path), tmp_path / "runs", seed_settings=True, git_baseline=True)
    tracked = set(git(wc.path, "ls-tree", "-r", "--name-only", "HEAD").split())
    assert tracked == {"calc.py", "pkg/util.py"}
    assert not (wc.path / ".git" / "hooks").exists()          # no sample hooks from templates


def test_pristine_with_history_is_refused(tmp_path):
    pristine = _task_layout(tmp_path)
    (pristine / ".git").mkdir()
    with pytest.raises(ValueError):
        make_working_copy(pristine, tmp_path / "runs", git_baseline=True)


class _Record:
    def __init__(self):
        self.seen = {}

    def run(self, working_copy, envelope, session, *, prompt=None, deadline=None):
        wc = working_copy.path
        self.seen.setdefault("head", bl.read_head(wc))
        self.seen.setdefault("tracked", git(wc, "ls-tree", "-r", "--name-only", "HEAD"))
        self.seen.setdefault("status", git(wc, "status", "--porcelain", "--untracked-files=all"))
        sid = session.session_id
        return AgentRunOutcome(exit_code=0, session_id=sid, agent_outcome=AgentOutcome.COMPLETED,
                               events=[{"type": "system", "subtype": "init", "session_id": sid},
                                       {"type": "result", "session_id": sid}])


def _lifecycle_run(tmp_path, config, pristine):
    home = tmp_path / config / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / config / "runs",
                        results_root=tmp_path / config / "results", home=home)
    runner = _Record()
    manifest = make_treated_manifest(config)
    result = life.execute(manifest=manifest, envelope=implementation_envelope(config),
                          session=SessionSpec("new", UUID), evaluator=SmokeEvaluator(),
                          agent_runner=runner, cleanup_runner=DryCleanupRunner(),
                          treatment=make_treatment(config), task_statement=TEST_STATEMENT)
    run_dir = tmp_path / config / "results" / manifest.run_id
    return result, runner.seen, run_dir


def test_b_c_same_neutral_baseline_for_c0_c1_c2_treatment_uncommitted(tmp_path):
    pristine = _task_layout(tmp_path)
    seen = {}
    for config in ("C0", "C1", "C2"):
        result, s, run_dir = _lifecycle_run(tmp_path, config, pristine)
        assert result.run_validity is RunValidity.VALID, result.invalid_reason
        rec = json.loads((run_dir / "baseline.json").read_text())
        assert rec["matches"] is True and rec["observed_commit"] == s["head"]
        seen[config] = s
    assert seen["C0"]["head"] == seen["C1"]["head"] == seen["C2"]["head"]
    assert seen["C0"]["tracked"] == seen["C1"]["tracked"] == seen["C2"]["tracked"]
    assert "CLAUDE.md" not in seen["C1"]["tracked"]
    # the treatment exists only as uncommitted working-copy material
    assert "?? CLAUDE.md" in seen["C1"]["status"] and "?? CLAUDE.md" in seen["C2"]["status"]
    assert "CLAUDE.md" not in seen["C0"]["status"]


def test_r_reference_and_hidden_material_absent_from_git_objects(tmp_path):
    pristine = _task_layout(tmp_path)
    _, _, _ = _lifecycle_run(tmp_path, "C1", pristine)
    wc = next((tmp_path / "C1" / "runs").iterdir())
    objects = subprocess.run(["git", "cat-file", "--batch-all-objects", "--batch"], cwd=str(wc),
                             env=bl._git_env(), stdout=subprocess.PIPE, check=True).stdout
    assert REF_MARKER.encode() not in objects and HIDDEN_MARKER.encode() not in objects
    assert git(wc, "rev-list", "--all", "--count").strip() == "1"
    assert git(wc, "stash", "list").strip() == "" and git(wc, "tag").strip() == ""


def test_baseline_mismatch_blocks_the_run(tmp_path, monkeypatch):
    pristine = _task_layout(tmp_path)
    monkeypatch.setattr(bl, "cached_expected_baseline_commit", lambda p: "0" * 40)
    result, seen, run_dir = _lifecycle_run(tmp_path, "C0", pristine)
    assert result.run_validity is RunValidity.PREFLIGHT_FAILED and seen == {}
    pre = json.loads((run_dir / "preflight.json").read_text())
    assert any(o["name"] == "baseline_commit" and o["status"] == "failed" for o in pre["outcomes"])
