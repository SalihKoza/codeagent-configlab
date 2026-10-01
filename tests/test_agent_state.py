"""G7 + treatment-state invariant: start-relative delta, final identity, drift detection."""

import json
import subprocess
from pathlib import Path

import pytest
from _helpers import TEST_CLAUDE_MD, TEST_STATEMENT, make_treated_manifest, make_treatment

from codeagent_configlab import baseline as bl
from codeagent_configlab.envelope import implementation_envelope
from codeagent_configlab.evaluator import SmokeEvaluator
from codeagent_configlab.lifecycle import AgentRunOutcome, DryCleanupRunner, RunLifecycle
from codeagent_configlab.orchestration import snapshot_tree
from codeagent_configlab.session import SessionSpec
from codeagent_configlab.status import Acceptance, AgentOutcome, C2Protocol, RunValidity

UUID = "abababab-1111-2222-3333-cdcdcdcdcdcd"


class Agent:
    """Applies ``phase_edits[i]`` in invocation ``i`` (0 = C0/C1 single or C2 phase 1)."""

    def __init__(self, *phase_edits):
        self.phase_edits, self.calls = list(phase_edits), 0

    def run(self, working_copy, envelope, session, *, prompt=None, deadline=None):
        edit = self.phase_edits[self.calls] if self.calls < len(self.phase_edits) else None
        self.calls += 1
        if edit:
            edit(working_copy.path)
        sid = session.session_id
        return AgentRunOutcome(exit_code=0, session_id=sid, agent_outcome=AgentOutcome.COMPLETED,
                               events=[{"type": "system", "subtype": "init", "session_id": sid},
                                       {"type": "result", "session_id": sid}])


def _pristine(tmp_path):
    p = tmp_path / "pristine"
    (p / "pkg").mkdir(parents=True)
    (p / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (p / "pkg" / "util.py").write_text("X = 1\n", encoding="utf-8")
    (p / "old_name.py").write_text("VALUE = 42\n", encoding="utf-8")
    (p / "obsolete.py").write_text("gone = True\n", encoding="utf-8")
    return p


def _run(tmp_path, config, agent, pristine=None):
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True, exist_ok=True)
    life = RunLifecycle(pristine=pristine or _pristine(tmp_path), runs_root=tmp_path / "runs",
                        results_root=tmp_path / "results", home=home)
    m = make_treated_manifest(config)
    result = life.execute(manifest=m, envelope=implementation_envelope(config),
                          session=SessionSpec("new", UUID), evaluator=SmokeEvaluator(),
                          agent_runner=agent, cleanup_runner=DryCleanupRunner(),
                          treatment=make_treatment(config), task_statement=TEST_STATEMENT)
    run_dir = tmp_path / "results" / m.run_id
    load = lambda n: json.loads((run_dir / n).read_text(encoding="utf-8"))  # noqa: E731
    return result, run_dir, load


def _typical_edit(wc: Path):
    (wc / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef multiply(a, b):\n"
                                "    return a * b\n", encoding="utf-8")
    (wc / "new_module.py").write_text("NEW = 1\n", encoding="utf-8")
    (wc / "obsolete.py").unlink()
    (wc / "old_name.py").rename(wc / "new_name.py")


@pytest.mark.parametrize("config", ["C0", "C1"])
def test_d_e_f_delta_relative_to_agent_start_state(tmp_path, config):
    result, run_dir, load = _run(tmp_path, config, Agent(_typical_edit))
    assert result.run_validity is RunValidity.VALID
    cf = load("changed_files.json")
    assert cf["relative_to"] == "agent_start_state"
    assert cf["added"] == ["new_module.py"]
    assert cf["modified"] == ["calc.py"]
    assert cf["deleted"] == ["obsolete.py"]
    assert cf["renamed"] == [["old_name.py", "new_name.py"]]
    patch = (run_dir / "final.diff").read_text(encoding="utf-8")
    assert "+def multiply(a, b):" in patch and "b/new_module.py" in patch
    assert "-gone = True" in patch and "renamed" in patch
    # intentional treatment and runtime seeds are not agent changes
    assert "CLAUDE.md" not in patch and ".claude/" not in patch
    start, final = load("start_state.json"), load("final_state.json")
    assert ("CLAUDE.md" in start["files"]) is (config == "C1")
    assert ".claude/settings.json" in start["files"]
    assert final["start_tree_hash"] == start["tree_hash"] != final["tree_hash"]
    assert final["head_commit"] == final["baseline_commit"] and final["head_moved"] is False
    assert result.artifacts.final_diff == "final.diff"


def test_no_op_run_has_empty_delta(tmp_path):
    result, run_dir, load = _run(tmp_path, "C1", Agent())
    cf = load("changed_files.json")
    assert cf["added"] == cf["modified"] == cf["deleted"] == cf["renamed"] == []
    assert (run_dir / "final.diff").read_text() == ""
    assert load("final_state.json")["tree_hash"] == load("start_state.json")["tree_hash"]


def test_agent_commit_is_visible_as_head_move(tmp_path):
    def commit(wc):
        _typical_edit(wc)
        subprocess.run(["git", "add", "-A"], cwd=wc, env=bl._git_env(), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "agent work"], cwd=wc, env=bl._git_env(), check=True)
    _, _, load = _run(tmp_path, "C0", Agent(commit))
    final = load("final_state.json")
    assert final["head_moved"] is True and final["head_commit"] != final["baseline_commit"]
    assert load("changed_files.json")["modified"] == ["calc.py"]   # delta is worktree-based


def test_evaluation_does_not_touch_the_canonical_final_state(tmp_path):
    class Mutating(SmokeEvaluator):
        def evaluate(self, final_working_copy):
            before = snapshot_tree(final_working_copy, ignore_dirs=())
            res = super().evaluate(final_working_copy)
            assert snapshot_tree(final_working_copy, ignore_dirs=()) == before
            return res
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    life = RunLifecycle(pristine=_pristine(tmp_path), runs_root=tmp_path / "runs",
                        results_root=tmp_path / "results", home=home)
    m = make_treated_manifest("C0")
    r = life.execute(manifest=m, envelope=implementation_envelope("C0"), session=SessionSpec("new", UUID),
                     evaluator=Mutating(), agent_runner=Agent(_typical_edit),
                     cleanup_runner=DryCleanupRunner(), task_statement=TEST_STATEMENT)
    assert r.acceptance is Acceptance.PASS


# ---------------------------------------------------------------- treatment drift ---------

@pytest.mark.parametrize("config", ["C1", "C2"])
def test_g_treatment_modified_or_deleted_is_drift(tmp_path, config):
    for name, edit in (("modify", lambda wc: (wc / "CLAUDE.md").write_bytes(b"changed\n")),
                       ("delete", lambda wc: (wc / "CLAUDE.md").unlink())):
        sub = tmp_path / name
        edits = (edit,) if config == "C1" else (None, edit)       # C2: during implementation
        result, run_dir, load = _run(sub, config, Agent(*edits))
        assert result.run_validity is RunValidity.INVALID_TREATMENT_DRIFT, (config, name)
        t = load("treatment.json")
        expected = {"modify": "modified CLAUDE.md", "delete": "deleted CLAUDE.md"}[name]
        assert t["ok"] is False and t["violations"] == [expected]
        wc = next((sub / "runs").iterdir())
        # nothing restored: the canonical state still shows what the agent did
        assert (wc / "CLAUDE.md").exists() is (name == "modify")
        assert "CLAUDE.md" in (run_dir / "final.diff").read_text()
        assert result.acceptance is not Acceptance.NOT_RUN          # diagnostic evaluation ran


@pytest.mark.parametrize("path", ["CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md",
                                  ".claude/rules/style.md", "pkg/CLAUDE.md", "pkg/.claude/rules/x.md",
                                  ".claude/settings.json", ".claude/settings.local.json",
                                  ".claude/agents/helper.md", ".claude/skills/s/SKILL.md",
                                  ".claude/commands/c.md"])
def test_h_c0_creating_or_changing_instruction_material_is_drift(tmp_path, path):
    def create(wc):
        target = wc / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"hooks": {}}\n' if path.endswith(".json") else "be different\n")
    result, run_dir, load = _run(tmp_path, "C0", Agent(create))
    assert result.run_validity is RunValidity.INVALID_TREATMENT_DRIFT
    assert any(path in v for v in load("treatment.json")["violations"])
    assert path in json.dumps(load("changed_files.json"))            # .claude/ is not invisible


def test_c2_phase1_instruction_write_is_a_c2_protocol_violation_first(tmp_path):
    result, _, _ = _run(tmp_path, "C2", Agent(lambda wc: (wc / "CLAUDE.md").write_bytes(b"x")))
    assert result.c2_protocol is C2Protocol.PHASE1_WRITE
    assert result.run_validity is RunValidity.INVALID_C2_PROTOCOL


@pytest.mark.parametrize("path", ["pkg/CLAUDE.md", ".claude/rules/x.md", ".claude/CLAUDE.md",
                                  "CLAUDE.local.md", ".claude/agents/a.md", ".claude/skills/s/SKILL.md"])
def test_i_fixture_shipping_instruction_material_fails_preflight(tmp_path, path):
    pristine = _pristine(tmp_path)
    target = pristine / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("shipped instructions\n")
    agent = Agent()
    result, run_dir, load = _run(tmp_path, "C1", agent, pristine=pristine)
    assert result.run_validity is RunValidity.PREFLIGHT_FAILED and agent.calls == 0
    detail = next(o for o in load("preflight.json")["outcomes"] if o["name"] == "treatment_instruction_files")
    assert detail["status"] == "failed" and path in detail["detail"]


def test_treatment_bytes_are_the_start_state_not_an_agent_change(tmp_path):
    _, _, load = _run(tmp_path, "C2", Agent(None, _typical_edit))
    start = load("start_state.json")
    from codeagent_configlab.hashing import sha256_bytes
    assert start["files"]["CLAUDE.md"] == sha256_bytes(TEST_CLAUDE_MD)
    assert "CLAUDE.md" not in json.dumps(load("changed_files.json"))
