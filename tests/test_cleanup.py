"""Cleanup command scoping: exact-name only, never broad ~/.claude or globs."""

import pytest

from codeagent_configlab.cleanup import (
    build_cleanup_plan,
    wc_slug,
    CleanupCommand,
    CleanupScopeError,
    plan_to_dict,
    verify_residue,
)

WC = "/home/cclab/cclab-bench/runs/ab12cd34ef567890"
UUID = "5b33c20b-5ae4-4a27-ba9a-16620954c6f3"


def test_plan_uses_purge_and_exact_rm_targets():
    plan = build_cleanup_plan(WC, [UUID], uid=1001)
    argvs = [c.argv for c in plan]
    assert ("claude", "project", "purge", "-y", WC) in argvs
    assert ("rm", "-rf", "--", f"/home/cclab/.claude/session-env/{UUID}") in argvs
    assert ("rm", "-rf", "--", f"/tmp/claude/claude-1001/{wc_slug(WC)}") in argvs


def test_no_command_targets_broad_claude_or_home():
    plan = build_cleanup_plan(WC, [UUID])
    for c in plan:
        for token in c.argv:
            assert token not in ("/home/cclab", "/home/cclab/.claude", "/home/cclab/.claude/", "~", "/")


def test_rejects_non_uuid_session_id():
    with pytest.raises(CleanupScopeError):
        build_cleanup_plan(WC, ["../../etc"], uid=1001)


def test_rejects_broad_working_copy():
    for bad in ("/", "/home/cclab", "/home/cclab/.claude", ""):
        with pytest.raises(CleanupScopeError):
            build_cleanup_plan(bad, [UUID])


def test_plan_serializes_for_report():
    d = plan_to_dict(build_cleanup_plan(WC, [UUID]))
    assert d["commands"][0]["argv"][0] == "claude"
    assert all("purpose" in c for c in d["commands"])


def test_slug_replaces_slashes_and_dots():
    assert "/" not in wc_slug(WC)
    assert wc_slug("/a/b.c") == "-a-b-c"


def _synthetic_plan(wc: str, uuid: str, uid: int, home: str) -> list[CleanupCommand]:
    """Same argv shape ``build_cleanup_plan`` would produce, without its hardcoded-``/home/cclab``
    scope guard -- only so ``verify_residue`` (a pure, independent function) can be exercised
    against a hermetic ``tmp_path``-based home instead of the real ``/home/cclab``."""
    return [
        CleanupCommand(argv=("claude", "project", "purge", "-y", wc),
                       purpose="remove project transcripts/memory/config entry for this working copy"),
        CleanupCommand(argv=("rm", "-rf", "--", f"{home}/.claude/session-env/{uuid}"),
                       purpose=f"remove exact session-env dir for {uuid}"),
        CleanupCommand(argv=("rm", "-rf", "--", f"/tmp/claude/claude-{uid}/{wc_slug(wc)}"),
                       purpose="remove exact per-project /tmp/claude dir"),
    ]


def test_verify_residue_all_clear_when_nothing_exists(tmp_path):
    home = tmp_path / "home"
    wc = str(tmp_path / "runs" / "ab12cd34ef567890")
    plan = _synthetic_plan(wc, UUID, 1001, str(home))
    residue = verify_residue(plan, home=str(home))
    assert residue["all_clear"] is True
    assert len(residue["targets"]) == 3  # purge-state dir + session-env dir + tmp-slug dir
    assert all(t["clear"] for t in residue["targets"])


def test_verify_residue_purge_target_uses_same_slug_as_rm_targets(tmp_path):
    home = tmp_path / "home"
    wc = str(tmp_path / "runs" / "ab12cd34ef567890")
    plan = _synthetic_plan(wc, UUID, 1001, str(home))
    residue = verify_residue(plan, home=str(home))
    purge_target = next(t for t in residue["targets"] if t["purpose"].startswith("remove project"))
    assert purge_target["target"] == f"{home}/.claude/projects/{wc_slug(wc)}"


def test_verify_residue_reports_a_leftover_path(tmp_path):
    home = tmp_path / "home"
    wc = str(tmp_path / "runs" / "ab12cd34ef567890")
    plan = _synthetic_plan(wc, UUID, 1001, str(home))
    session_env_target = next(c for c in plan if "session-env" in c.argv[-1]).argv[-1]
    (tmp_path / "home" / ".claude" / "session-env" / UUID).mkdir(parents=True)
    assert (tmp_path / "home" / ".claude" / "session-env" / UUID).exists()
    residue = verify_residue(plan, home=str(home))
    assert residue["all_clear"] is False
    leftover = next(t for t in residue["targets"] if t["target"] == session_env_target)
    assert leftover["clear"] is False
