"""Artifact allowlist, secret-marker non-leakage, and schemas free of secret fields."""

import pytest

from codeagent_configlab.artifacts import (
    ArtifactStore,
    ArtifactNameError,
    ArtifactSecretError,
    scan_for_secrets,
    schema_has_no_secret_fields,
)
from codeagent_configlab._schemas import load_schema


def test_only_allowlisted_names_are_writable(tmp_path):
    store = ArtifactStore.create(tmp_path, "run_x")
    store.write_text("stdout.txt", "hello")
    with pytest.raises(ArtifactNameError):
        store.write_text("passwords.txt", "nope")


def test_secret_markers_are_refused(tmp_path):
    store = ArtifactStore.create(tmp_path, "run_x", extra_secret_markers=("CANARY-XYZ",))
    with pytest.raises(ArtifactSecretError):
        store.write_text("stdout.txt", "leaked sk-ant-abc123")
    with pytest.raises(ArtifactSecretError):
        store.write_text("stdout.txt", "path /home/cclab/.claude/.credentials.json")
    with pytest.raises(ArtifactSecretError):
        store.write_text("stdout.txt", "run-specific CANARY-XYZ here")


def test_clean_text_writes_and_ref_is_relative(tmp_path):
    store = ArtifactStore.create(tmp_path, "run_x")
    p = store.write_text("stdout.txt", "all clean output")
    assert p.exists()
    assert store.ref("stdout.txt") == "stdout.txt"


def test_scan_dir_finds_planted_leak(tmp_path):
    store = ArtifactStore.create(tmp_path, "run_x")
    # write a benign file directly, then plant a marker bypassing write_text
    (store.run_dir / "events.jsonl").write_text('{"x": "sk-ant-zzz"}', encoding="utf-8")
    leaks = store.scan_dir_for_secrets()
    assert "events.jsonl" in leaks


def test_scan_for_secrets_reports_all_markers():
    found = scan_for_secrets("sk-ant-1 and CRED2-CANARY-abc")
    assert "sk-ant-" in found and "CRED2-CANARY" in found


def test_manifest_and_result_schemas_have_no_secret_fields():
    for name in ("run-manifest.schema.json", "run-result.schema.json"):
        assert schema_has_no_secret_fields(load_schema(name)) is None, name
