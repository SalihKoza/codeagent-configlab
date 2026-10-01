"""Clean working-copy primitive: pristine immutability, freshness, opaque path, baseline hash."""

from pathlib import Path

import pytest

from codeagent_configlab.hashing import tree_hash
from codeagent_configlab.workspace import (
    make_working_copy,
    check_ancestor_instructions,
    changed_files,
    seed_wc_settings,
)


def _pristine(tmp_path: Path) -> Path:
    p = tmp_path / "pristine"
    p.mkdir()
    (p / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    return p


def test_working_copy_is_fresh_opaque_and_pristine_unchanged(tmp_path):
    pristine = _pristine(tmp_path)
    before = tree_hash(pristine)
    runs = tmp_path / "runs"
    wc = make_working_copy(pristine, runs, seed_settings=False)

    assert wc.path.exists() and (wc.path / "calc.py").exists()
    assert wc.path.parent == runs
    # opaque token name: 16 hex chars, encodes nothing
    assert wc.path.name == wc.token and len(wc.token) == 16
    # pristine untouched
    assert tree_hash(pristine) == before
    # baseline is hashable and matches the copy
    assert wc.baseline_hash == tree_hash(wc.path)


def test_explicit_token_is_used_as_dir_name(tmp_path):
    pristine = _pristine(tmp_path)
    wc = make_working_copy(pristine, tmp_path / "runs", seed_settings=False, token="feedface12345678")
    assert wc.token == "feedface12345678"
    assert wc.path.name == "feedface12345678"


def test_invalid_token_rejected(tmp_path):
    pristine = _pristine(tmp_path)
    # "" is falsy → mint a fresh token (documented), so it is not "invalid"; separators and
    # dot-dirs are rejected.
    for bad in ("../escape", "a/b", "a\\b", "..", "."):
        with pytest.raises(ValueError):
            make_working_copy(pristine, tmp_path / "runs", token=bad)


def test_lifecycle_wc_dir_matches_manifest_workspace_token(tmp_path):
    # provenance: the on-disk WC dir name equals the manifest's workspace_token
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _helpers import make_manifest
    from codeagent_configlab.envelope import implementation_envelope
    from codeagent_configlab.evaluator import SmokeEvaluator
    from codeagent_configlab.lifecycle import DryAgentRunner, RunLifecycle
    from codeagent_configlab.session import SessionSpec

    pristine = _pristine(tmp_path)
    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    m = make_manifest("C0")
    life.execute(manifest=m, envelope=implementation_envelope("C0"),
                 session=SessionSpec("new", "77777777-7777-7777-7777-777777777777"),
                 evaluator=SmokeEvaluator(), agent_runner=DryAgentRunner())
    assert (tmp_path / "runs" / m.workspace_token).is_dir()


def test_each_copy_is_distinct(tmp_path):
    pristine = _pristine(tmp_path)
    runs = tmp_path / "runs"
    a = make_working_copy(pristine, runs, seed_settings=False)
    b = make_working_copy(pristine, runs, seed_settings=False)
    assert a.path != b.path and a.token != b.token


def test_seed_wc_settings_adds_empty_claude_settings(tmp_path):
    pristine = _pristine(tmp_path)
    wc = make_working_copy(pristine, tmp_path / "runs", seed_settings=True)
    assert (wc.path / ".claude" / "settings.json").read_text().strip() == "{}"
    assert (wc.path / ".claude" / "settings.local.json").exists()


def test_changed_files_ignores_seeded_settings_and_reports_edits(tmp_path):
    pristine = _pristine(tmp_path)
    wc = make_working_copy(pristine, tmp_path / "runs", seed_settings=True)
    # seeding alone is not an agent change
    assert changed_files(pristine, wc.path) == {"added": [], "modified": [], "deleted": []}
    # simulate an agent edit + new file
    (wc.path / "calc.py").write_text("def add(a, b):\n    return a + b\n\ndef mul(a,b):\n    return a*b\n", encoding="utf-8")
    (wc.path / "new.txt").write_text("x", encoding="utf-8")
    cf = changed_files(pristine, wc.path)
    assert cf["modified"] == ["calc.py"]
    assert cf["added"] == ["new.txt"]
    assert cf["deleted"] == []


def test_refuses_fixture_with_forbidden_material(tmp_path):
    pristine = _pristine(tmp_path)
    (pristine / "reference_solution").mkdir()
    with pytest.raises(ValueError):
        make_working_copy(pristine, tmp_path / "runs")


def test_ancestor_instruction_detection(tmp_path):
    pristine = _pristine(tmp_path)
    wc = make_working_copy(pristine, tmp_path / "runs", seed_settings=False)
    assert check_ancestor_instructions(wc.path) == []
    # placing a CLAUDE.md above the working copy must be detected
    (tmp_path / "CLAUDE.md").write_text("instructions", encoding="utf-8")
    found = check_ancestor_instructions(wc.path)
    assert any(p.name == "CLAUDE.md" for p in found)
