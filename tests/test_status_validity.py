"""Status taxonomy: axes stay separate; a legitimate task failure is NOT an invalid run."""

from codeagent_configlab.status import (
    AgentOutcome,
    RunValidity,
    Acceptance,
    Regression,
    Integrity,
    C2Protocol,
    INVALID_VALUES,
    is_valid,
    is_resolved,
)


def test_task_failure_is_valid_not_invalid():
    # agent completed, tests failed -> a real experimental outcome, still VALID
    assert is_valid(RunValidity.VALID)
    assert not is_resolved(RunValidity.VALID, Acceptance.FAIL, Regression.PASS, Integrity.CLEAN)


def test_resolved_requires_all_axes():
    assert is_resolved(RunValidity.VALID, Acceptance.PASS, Regression.PASS, Integrity.CLEAN)
    assert not is_resolved(RunValidity.INVALID_LEAK, Acceptance.PASS, Regression.PASS, Integrity.CLEAN)
    assert not is_resolved(RunValidity.VALID, Acceptance.PASS, Regression.FAIL, Integrity.CLEAN)
    assert not is_resolved(RunValidity.VALID, Acceptance.PASS, Regression.PASS, Integrity.PROTECTED_PATH_MODIFIED)


def test_invalid_values_exclude_valid_only():
    assert RunValidity.VALID not in INVALID_VALUES
    assert RunValidity.INVALID_HARNESS in INVALID_VALUES
    assert RunValidity.PREFLIGHT_FAILED in INVALID_VALUES


def test_integrity_violation_is_an_outcome_not_invalid():
    # protocol §6/F13: agent integrity violations are outcomes, the run stays valid
    assert is_valid(RunValidity.VALID)
    assert not is_resolved(RunValidity.VALID, Acceptance.PASS, Regression.PASS, Integrity.OUT_OF_TREE_WRITE_DETECTED)


def test_enum_string_values_match_protocol():
    assert AgentOutcome.LIMIT_INTERRUPTED.value == "limit_interrupted"
    assert RunValidity.INVALID_C2_PROTOCOL.value == "invalid:c2_protocol"
    assert C2Protocol.PHASE1_WRITE.value == "phase1_write"
