"""Policy/settings hash recording, and parity with setup/common.sh auth-var list."""

import re

from _helpers import make_manifest

from codeagent_configlab.envelope import AUTH_OVERRIDE_VARS, SecurityPolicy, implementation_envelope


def test_manifest_records_policy_and_settings_hashes():
    m = make_manifest("C2")
    assert m.security_policy_hash == SecurityPolicy().policy_hash()
    assert m.settings_policy_hash == implementation_envelope("C2").envelope_hash()
    # hashes are stable, non-empty, and hex
    assert re.fullmatch(r"[0-9a-f]{64}", m.security_policy_hash)
    assert re.fullmatch(r"[0-9a-f]{64}", m.settings_policy_hash)


def test_policy_hash_changes_if_credential_path_changes():
    a = SecurityPolicy().policy_hash()
    b = SecurityPolicy(credential_path="/somewhere/else").policy_hash()
    assert a != b


def test_auth_override_vars_match_setup_common_sh(repo_root):
    """The harness sanitizes exactly the variables setup/common.sh declares (protocol §3.1)."""
    common = (repo_root / "setup" / "common.sh").read_text(encoding="utf-8")
    m = re.search(r"CCLAB_AUTH_OVERRIDE_VARS=\((.*?)\)", common, re.DOTALL)
    assert m, "could not find CCLAB_AUTH_OVERRIDE_VARS in setup/common.sh"
    declared = tuple(tok for tok in m.group(1).split() if tok and not tok.startswith("#"))
    assert declared == AUTH_OVERRIDE_VARS


def test_security_policy_defaults_are_the_accepted_v0_posture():
    p = SecurityPolicy()
    assert p.outer_allow_all_unix_sockets is True        # the single Candidate-2 outer delta
    assert p.inner_sandbox_enabled is True
    assert p.fail_if_unavailable is True
    assert p.allow_unsandboxed_commands is False
    assert p.seed_wc_settings is True
    assert p.permission_deny_tools == ("Read", "Edit")   # Write() inert in 2.1.263
