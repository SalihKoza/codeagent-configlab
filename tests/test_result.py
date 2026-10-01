"""Result-record validation and manifest/result separation."""

from codeagent_configlab.result import RunResult, ArtifactRefs
from codeagent_configlab.status import (
    AgentOutcome,
    RunValidity,
    Acceptance,
    Regression,
    Integrity,
    C2Protocol,
)


def _valid_result() -> RunResult:
    return RunResult(
        run_id="run_test",
        started_at="2026-09-25T00:00:00Z",
        ended_at="2026-09-25T00:01:00Z",
        duration_seconds=60.0,
        agent_exit_code=0,
        observed_session_id="uuid-x",
        session_continuity_verified=True,
        agent_outcome=AgentOutcome.COMPLETED,
        run_validity=RunValidity.VALID,
        acceptance=Acceptance.PASS,
        regression=Regression.PASS,
        integrity=Integrity.CLEAN,
        c2_protocol=C2Protocol.NOT_APPLICABLE,
        artifacts=ArtifactRefs(evaluator="evaluator.json"),  # G8: a verdict must be auditable
    )


def test_valid_result_document():
    assert _valid_result().validate() == []


def test_result_enums_serialize_to_protocol_strings():
    d = _valid_result().to_dict()
    assert d["agent_outcome"] == "completed"
    assert d["run_validity"] == "valid"
    assert d["acceptance"] == "pass"
    assert d["c2_protocol"] == "not_applicable"


def test_invalid_enum_value_is_rejected_by_schema():
    d = _valid_result().to_dict()
    d["agent_outcome"] = "not_a_real_outcome"
    r = RunResult(run_id="x")
    from codeagent_configlab import schema as s
    from codeagent_configlab._schemas import load_schema

    assert s.validate(d, load_schema("run-result.schema.json"))


def test_artifact_refs_are_relative_logical_paths():
    r = _valid_result()
    r.artifacts = ArtifactRefs(stdout="stdout.txt", final_diff="final.diff")
    d = r.to_dict()
    assert d["artifacts"]["stdout"] == "stdout.txt"
    assert "/" not in (d["artifacts"]["stdout"] or "")
