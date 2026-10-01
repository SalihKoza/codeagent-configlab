"""Smoke manifest/namespace, CLI shape, and lifecycle cleanup-failure recording."""

from pathlib import Path

import pytest

from _helpers import make_manifest

from codeagent_configlab.envelope import implementation_envelope
from codeagent_configlab.evaluator import SmokeEvaluator
from codeagent_configlab.lifecycle import DryAgentRunner, RunLifecycle
from codeagent_configlab.session import SessionSpec
from codeagent_configlab.smoke import (
    SMOKE_NAMESPACE,
    SMOKE_TASK_ID,
    build_smoke_manifest,
    default_harness_root,
)


def test_smoke_manifest_is_valid_c0_and_non_final():
    m = build_smoke_manifest(model="haiku")
    assert m.validate() == []
    assert m.configuration == "C0"
    assert m.claude_md_hash is None and m.planning_tool_set is None
    # explicitly non-final: provisional model + labelled task id (not one of the six tasks)
    assert m.model_request == "haiku"
    assert m.task_id == SMOKE_TASK_ID and "SMOKE" in SMOKE_TASK_ID


def test_smoke_namespace_distinct_from_final():
    assert SMOKE_NAMESPACE == "HARNESS_SMOKE_ONLY"
    # the smoke root is a dedicated, obviously-smoke location, not a generic results store
    assert "smoke" in str(default_harness_root()).lower()


def test_cli_exposes_only_smoke():
    from codeagent_configlab.__main__ import main

    # no subcommand -> argparse error (SystemExit), i.e. nothing runs by default
    with pytest.raises(SystemExit):
        main([])
    with pytest.raises(SystemExit):
        main(["run-benchmark"])  # there is no such command


def test_lifecycle_records_cleanup_failure(tmp_path):
    class FailingCleanup:
        def execute(self, plan):
            return {"commands": [{"argv": list(plan[0].argv), "exit": 1, "ok": False}],
                    "executed": False, "cleanup_failed": True}

    pristine = tmp_path / "pristine"
    pristine.mkdir()
    (pristine / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    life = RunLifecycle(pristine=pristine, runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    manifest = make_manifest("C0")
    result = life.execute(
        manifest=manifest, envelope=implementation_envelope("C0"),
        session=SessionSpec("new", "99999999-9999-9999-9999-999999999999"),
        evaluator=SmokeEvaluator(),
        agent_runner=DryAgentRunner(mutate=lambda wc: (wc / "calc.py").write_text(
            "def add(a,b):\n return a+b\ndef multiply(a,b):\n return a*b\n", encoding="utf-8")),
        cleanup_runner=FailingCleanup(),
    )
    # the run itself is fine; cleanup failure is recorded, not silently ignored
    assert result.cleanup.performed is False
    report = (tmp_path / "results" / manifest.run_id / "cleanup.json").read_text()
    assert "cleanup_failed" in report  # the runner-reported failure is persisted
