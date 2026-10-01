"""Execution-envelope invariants and Candidate-2 policy rendering."""

from codeagent_configlab.envelope import (
    ExecutionEnvelope,
    SecurityPolicy,
    implementation_envelope,
    planning_envelope,
    IMPLEMENTATION_TOOLS,
    PLANNING_TOOLS,
)
from codeagent_configlab.session import SessionSpec


def test_implementation_envelope_equal_across_c0_c1_c2():
    e0 = implementation_envelope("C0")
    e1 = implementation_envelope("C1")
    e2 = implementation_envelope("C2")
    # The invariant: the implementation envelope is identical across configurations
    # (CLAUDE.md is a fixture-file treatment, not a CLI flag).
    assert e0 == e1 == e2
    assert e0.identity_dict() == e1.identity_dict() == e2.identity_dict()
    assert e0.envelope_hash() == e1.envelope_hash() == e2.envelope_hash()


def test_planning_envelope_differs_only_in_tools_and_ro():
    impl = implementation_envelope("C2")
    plan = planning_envelope()
    assert plan.tools == PLANNING_TOOLS
    assert impl.tools == IMPLEMENTATION_TOOLS
    assert plan.srt_mode == "ro" and impl.srt_mode == "impl"
    # Every other identity field (permission mode, mcp, setting-sources, output, security policy)
    # must be identical — planning differs ONLY by the treatment.
    a = plan.identity_dict()
    b = impl.identity_dict()
    differing = {k for k in a if a[k] != b[k]}
    assert differing == {"phase", "tools", "srt_mode"}


def test_planning_and_impl_share_identical_security_policy():
    assert planning_envelope().security_policy == implementation_envelope("C0").security_policy


def test_bad_configuration_rejected():
    import pytest

    with pytest.raises(ValueError):
        implementation_envelope("C3")


def test_inner_settings_shape_matches_candidate2():
    pol = SecurityPolicy()
    s = pol.render_inner_settings("/home/cclab", "/wc", "/tmp/run")
    sb = s["sandbox"]
    assert sb["enabled"] is True
    assert sb["failIfUnavailable"] is True
    assert sb["allowUnsandboxedCommands"] is False
    assert sb["autoAllowBashIfSandboxed"] is False
    assert sb["credentials"]["files"] == [{"path": pol.credential_path, "mode": "deny"}]
    # allowWrite MUST include WC + TMP (else Bash bwrap fails — Candidate-2 finding)
    assert sb["filesystem"]["allowWrite"] == ["/wc", "/tmp/run"]
    assert sb["filesystem"]["denyRead"] == [pol.credential_path]
    # built-in denies: Read()+Edit() only (Write() is inert in 2.1.263), plus the glob
    deny = s["permissions"]["deny"]
    assert f"Read(/{pol.credential_path})" in deny
    assert f"Edit(/{pol.credential_path})" in deny
    assert "Read(**/.credentials.json)" in deny
    assert not any(d.startswith("Write(") for d in deny)


def test_outer_srt_relaxation_and_modes():
    pol = SecurityPolicy()
    impl = pol.render_outer_srt("impl", "/home/cclab", "/harness", "/wc", "/tmp/run")
    ro = pol.render_outer_srt("ro", "/home/cclab", "/harness", "/wc", "/tmp/run")
    # the single Candidate-2 delta is present
    assert impl["network"]["allowAllUnixSockets"] is True
    # /mnt/c and the harness root stay denied for reading in both modes
    assert "/mnt/c" in impl["filesystem"]["denyRead"] and "/harness" in impl["filesystem"]["denyRead"]
    # impl: WC writable; ro (C2 phase 1): WC in denyWrite (read-only treatment)
    # impl: WC writable except the G11-active <wc>/.claude, which is write-protected in every phase
    assert "/wc" in impl["filesystem"]["allowWrite"] and impl["filesystem"]["denyWrite"] == ["/wc/.claude"]
    assert ro["filesystem"]["denyWrite"] == ["/wc"] and "/wc" not in ro["filesystem"]["allowWrite"]


def test_claude_flags_use_session_id_and_resume_not_continue_or_fork():
    impl = implementation_envelope("C0")
    new = impl.build_claude_flags(model="M", effort="high", session_flag=SessionSpec("new", "u").cli_flag(), protect_json="{}", add_dir="/wc")
    res = impl.build_claude_flags(model="M", effort="high", session_flag=SessionSpec("resume", "u").cli_flag(), protect_json="{}", add_dir="/wc")
    assert "--session-id" in new and "u" in new
    assert "--resume" in res
    for bad in ("--continue", "--fork-session"):
        assert bad not in new and bad not in res
    assert "--strict-mcp-config" in new
    assert new[new.index("--setting-sources") + 1] == ""  # no user/project/local settings
    assert new[new.index("--effort") + 1] == "high"


def test_policy_hash_is_stable_and_changes_with_posture():
    base = SecurityPolicy()
    assert base.policy_hash() == SecurityPolicy().policy_hash()
    weakened = SecurityPolicy(allow_unsandboxed_commands=True)
    assert weakened.policy_hash() != base.policy_hash()


# --- G11: common instruction loader + write-protected <wc>/.claude ------------------------

import pytest  # noqa: E402

from codeagent_configlab.envelope import INSTRUCTION_LOADER, INSTRUCTION_LOADER_ENV, planning_envelope  # noqa: E402


def test_g11_loader_identical_for_every_configuration_and_phase():
    envs = [implementation_envelope(c) for c in ("C0", "C1", "C2")] + [planning_envelope()]
    assert {e.instruction_loader for e in envs} == {INSTRUCTION_LOADER}
    assert all(e.loader_env() == INSTRUCTION_LOADER_ENV for e in envs)
    assert INSTRUCTION_LOADER_ENV == {"CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "1"}
    assert {e.setting_sources for e in envs} == {""}          # project/local settings stay inactive
    ids = [e.identity_dict() for e in envs]
    assert all(i["instruction_loader"] == INSTRUCTION_LOADER for i in ids)


def test_g11_flags_add_the_working_copy_and_keep_empty_setting_sources():
    for env in (implementation_envelope("C1"), planning_envelope()):
        flags = env.build_claude_flags(model="M", effort="high", session_flag=("--session-id", "u"),
                                       protect_json="{}", add_dir="/runs/abc")
        assert flags[flags.index("--add-dir") + 1] == "/runs/abc"
        assert flags[flags.index("--setting-sources") + 1] == ""
        assert "--system-prompt-file" not in flags and "--append-system-prompt-file" not in flags
        with pytest.raises(ValueError):
            env.build_claude_flags(model="M", effort="high", session_flag=("--session-id", "u"),
                                   protect_json="{}")


def test_g11_dot_claude_protected_in_outer_inner_and_permission_layers():
    pol = SecurityPolicy()
    assert "protected_wc_subpaths" in pol.identity_dict()
    inner = pol.render_inner_settings("/home/cclab", "/runs/abc", "/tmp/run")
    assert inner["sandbox"]["filesystem"]["denyWrite"] == ["/runs/abc/.claude"]
    assert "Edit(//runs/abc/.claude/**)" in inner["permissions"]["deny"]
    # credential controls unchanged
    assert "Read(//home/cclab/.claude/.credentials.json)" in inner["permissions"]["deny"]
    assert inner["sandbox"]["filesystem"]["denyRead"] == [pol.credential_path]
    outer_impl = pol.render_outer_srt("impl", "/home/cclab", "/h", "/runs/abc", "/tmp/run")
    outer_ro = pol.render_outer_srt("ro", "/home/cclab", "/h", "/runs/abc", "/tmp/run")
    assert outer_impl["filesystem"]["denyWrite"] == ["/runs/abc/.claude"]
    assert outer_ro["filesystem"]["denyWrite"] == ["/runs/abc"]     # whole WC read-only in phase 1
