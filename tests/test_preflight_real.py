"""Real run-start preflight: clean vs contaminated; old projects don't false-positive."""

from pathlib import Path

from codeagent_configlab.preflight import (
    PreflightContext,
    run_preflight,
    run_start_checks,
    _project_slug,
)
from codeagent_configlab.workspace import make_working_copy


def _fresh(tmp_path):
    pristine = tmp_path / "pristine"
    pristine.mkdir()
    (pristine / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    (home / ".claude" / "session-env").mkdir(parents=True)
    wc = make_working_copy(pristine, tmp_path / "runs", seed_settings=True)
    return pristine, home, wc


def _ctx(pristine, home, wc, uuid="aaaaaaaa-1111-2222-3333-444444444444", uid=4321):
    return PreflightContext(
        working_copy=wc.path, home=home, pristine=pristine,
        harness_root=pristine.parent, session_uuid=uuid, uid=uid,
    )


def test_clean_run_start_passes(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    rep = run_preflight(_ctx(pristine, home, wc), run_start_checks())
    assert rep.ok, rep.to_dict()
    assert rep.deferred == []  # real run has no DEFERRED checks


def test_seeded_settings_not_flagged(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    # the WC has .claude/settings.json from seeding; must NOT count as a modification
    rep = run_preflight(_ctx(pristine, home, wc), run_start_checks())
    wc_check = next(o for o in rep.outcomes if o.name == "working_copy_unmodified")
    assert wc_check.status.value == "ok"


def test_user_level_claude_md_fails(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    (home / ".claude" / "CLAUDE.md").write_text("x", encoding="utf-8")
    rep = run_preflight(_ctx(pristine, home, wc), run_start_checks())
    assert not rep.ok
    assert any(o.name == "user_level_instructions" and o.status.value == "failed" for o in rep.outcomes)


def test_preexisting_project_state_fails(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    (home / ".claude" / "projects" / _project_slug(wc.path)).mkdir(parents=True)
    rep = run_preflight(_ctx(pristine, home, wc), run_start_checks())
    assert any(o.name == "no_project_state" and o.status.value == "failed" for o in rep.outcomes)


def test_old_unrelated_project_does_not_fail(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    # an unrelated old smoke project exists; it must NOT block the new run
    (home / ".claude" / "projects" / "-tmp-cclab-claude-smoke-OLD").mkdir(parents=True)
    rep = run_preflight(_ctx(pristine, home, wc), run_start_checks())
    assert rep.ok, rep.to_dict()


def test_preexisting_session_env_fails(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    uuid = "bbbbbbbb-1111-2222-3333-444444444444"
    (home / ".claude" / "session-env" / uuid).mkdir(parents=True)
    rep = run_preflight(_ctx(pristine, home, wc, uuid=uuid), run_start_checks())
    assert any(o.name == "no_session_env" and o.status.value == "failed" for o in rep.outcomes)


def test_working_copy_modified_fails(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    (wc.path / "calc.py").write_text("def add(a,b):\n return 999\n", encoding="utf-8")
    rep = run_preflight(_ctx(pristine, home, wc), run_start_checks())
    assert any(o.name == "working_copy_unmodified" and o.status.value == "failed" for o in rep.outcomes)


# --- G9: treatment-aware instruction-file checks -------------------------------------------
import pytest  # noqa: E402

from codeagent_configlab.hashing import sha256_bytes  # noqa: E402

TREATMENT = b"# test-only treatment\n"
EXPECTED = {"CLAUDE.md": sha256_bytes(TREATMENT)}


def _status(rep, name):
    return next(o for o in rep.outcomes if o.name == name).status.value


def _treated_ctx(pristine, home, wc, expected):
    ctx = _ctx(pristine, home, wc)
    ctx.expected_treatment_files = dict(expected)
    return ctx


def test_f_c1_c2_exact_treatment_passes(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    (wc.path / "CLAUDE.md").write_bytes(TREATMENT)
    rep = run_preflight(_treated_ctx(pristine, home, wc, EXPECTED), run_start_checks())
    assert rep.ok, rep.to_dict()
    assert _status(rep, "working_copy_unmodified") == "ok"      # treatment is not "added"


@pytest.mark.parametrize("setup,why", [
    (lambda wc: None, "missing"),
    (lambda wc: (wc / "CLAUDE.md").write_bytes(b"tampered\n"), "hash mismatch"),
    (lambda wc: ((wc / "CLAUDE.md").write_bytes(TREATMENT),
                 (wc / "CLAUDE.local.md").write_text("extra")), "extra local instructions"),
])
def test_f_wrong_missing_or_extra_treatment_fails(tmp_path, setup, why):
    pristine, home, wc = _fresh(tmp_path)
    setup(wc.path)
    rep = run_preflight(_treated_ctx(pristine, home, wc, EXPECTED), run_start_checks())
    assert not rep.ok, why
    assert _status(rep, "treatment_instruction_files") == "failed"


def test_g_c0_root_claude_md_fails(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    (wc.path / "CLAUDE.md").write_bytes(TREATMENT)
    rep = run_preflight(_treated_ctx(pristine, home, wc, {}), run_start_checks())
    assert _status(rep, "treatment_instruction_files") == "failed"
    assert _status(rep, "working_copy_unmodified") == "failed"


def test_g_default_context_is_strict_like_c0(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    (wc.path / "CLAUDE.md").write_bytes(TREATMENT)
    rep = run_preflight(_ctx(pristine, home, wc), run_start_checks())
    assert not rep.ok


def test_g_pristine_shipping_claude_md_fails_even_for_c1(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    (pristine / "CLAUDE.md").write_bytes(TREATMENT)
    (wc.path / "CLAUDE.md").write_bytes(TREATMENT)
    rep = run_preflight(_treated_ctx(pristine, home, wc, EXPECTED), run_start_checks())
    assert _status(rep, "treatment_instruction_files") == "failed"


@pytest.mark.parametrize("expected", [{}, EXPECTED])
def test_h_parent_and_user_level_contamination_still_fail(tmp_path, expected):
    pristine, home, wc = _fresh(tmp_path)
    if expected:
        (wc.path / "CLAUDE.md").write_bytes(TREATMENT)
    (wc.path.parent / "CLAUDE.md").write_text("parent instructions")   # directory above the WC
    (home / ".claude" / "CLAUDE.md").write_text("user instructions")
    rep = run_preflight(_treated_ctx(pristine, home, wc, expected), run_start_checks())
    assert _status(rep, "ancestor_instruction_files") == "failed"
    assert _status(rep, "user_level_instructions") == "failed"
    if expected:
        assert _status(rep, "treatment_instruction_files") == "ok"   # the treatment itself is fine


def test_h_default_checks_also_catch_parent_claude_md(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    (wc.path.parent / "CLAUDE.local.md").write_text("x")
    rep = run_preflight(_ctx(pristine, home, wc))   # DEFAULT_CHECKS
    assert _status(rep, "ancestor_instruction_files") == "failed"


def test_provenance_errors_fail_preflight(tmp_path):
    pristine, home, wc = _fresh(tmp_path)
    ctx = _ctx(pristine, home, wc)
    ctx.provenance_errors = ["approval message does not match manifest.approval_message_hash"]
    rep = run_preflight(ctx, run_start_checks())
    assert _status(rep, "treatment_provenance") == "failed"
