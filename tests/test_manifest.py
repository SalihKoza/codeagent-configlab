"""Manifest validation: schema conformance, OPEN/NA semantics, config-conditional rules."""

from _helpers import make_manifest

from codeagent_configlab.manifest import RunManifest
from codeagent_configlab.sentinels import OPEN


def test_c0_manifest_is_valid_and_has_open_and_na_fields():
    m = make_manifest("C0")
    assert m.validate() == []
    # OPEN (undecided) defaults are the visible sentinel, not a fake value.
    assert m.model_request == OPEN
    assert m.effort_request == OPEN
    assert m.timeout_seconds == OPEN
    # N/A (not applicable to C0) fields are null.
    assert m.claude_md_hash is None
    assert m.planning_tool_set is None
    assert m.planning_wrapper_hash is None
    assert m.approval_message_hash is None


def test_c1_requires_claude_md_and_no_planning_fields():
    assert make_manifest("C1").validate() == []
    bad = make_manifest("C1", claude_md_hash=None)
    assert any("claude_md_hash" in e for e in bad.validate())
    bad2 = make_manifest("C1", planning_tool_set=("Bash",))
    assert any("planning_tool_set" in e for e in bad2.validate())


def test_c2_requires_planning_fields():
    assert make_manifest("C2").validate() == []
    for field in ("planning_tool_set", "planning_wrapper_hash", "approval_message_hash"):
        bad = make_manifest("C2", **{field: None})
        assert any(field in e for e in bad.validate()), field


def test_c0_with_claude_md_is_rejected():
    bad = make_manifest("C0", claude_md_hash="x" * 64)
    assert any("claude_md_hash" in e for e in bad.validate())


def test_roundtrip_to_from_dict():
    for cfg in ("C0", "C1", "C2"):
        m = make_manifest(cfg)
        assert RunManifest.from_dict(m.to_dict()).to_dict() == m.to_dict()


def test_schema_rejects_unknown_and_missing_fields():
    m = make_manifest("C0")
    d = m.to_dict()
    d["surprise"] = 1
    from codeagent_configlab import schema as s
    from codeagent_configlab._schemas import load_schema

    assert s.validate(d, load_schema("run-manifest.schema.json"))  # non-empty errors
    d.pop("surprise")
    d.pop("created_at")
    assert s.validate(d, load_schema("run-manifest.schema.json"))


def test_model_request_can_be_frozen_to_real_value():
    m = make_manifest("C0", model_request="claude-haiku-4-5-20251001", timeout_seconds=900)
    assert m.validate() == []


def test_effort_request_can_be_frozen_to_real_value():
    m = make_manifest("C0", model_request="claude-sonnet-5", effort_request="high",
                      timeout_seconds=900)
    assert m.validate() == []
    assert m.effort_request == "high"


def test_invalid_effort_level_is_rejected():
    bad = make_manifest("C0", effort_request="ultra")
    assert any("effort_request" in e for e in bad.validate())


def test_default_literal_model_is_rejected():
    for literal in ("Default", "default", "DEFAULT"):
        bad = make_manifest("C0", model_request=literal)
        errs = bad.validate()
        assert any("Default" in e for e in errs), (literal, errs)
