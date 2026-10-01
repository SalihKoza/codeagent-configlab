"""The run result — observed output of one run, kept separate from the manifest.

Runtime observations never mutate the immutable specification (protocol §7). Artifact
references are *relative logical paths* inside the run's artifact directory, never absolute
host paths, and never secret values. No token/cost/usage metric is part of this required
schema (protocol §7 / O8): the meaning of any usage fields the CLI emits is not yet frozen, so
they are captured elsewhere until then.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import RESULT_SCHEMA_VERSION
from ._schemas import load_schema
from . import schema as _schema
from .status import (
    AgentOutcome,
    RunValidity,
    Acceptance,
    Regression,
    Integrity,
    C2Protocol,
    analysis_eligibility_dict,
    check_status_consistency,
)


@dataclass
class ArtifactRefs:
    """Relative logical references to captured artifacts (or None if not produced)."""

    stdout: Optional[str] = None
    stderr: Optional[str] = None
    events: Optional[str] = None
    final_diff: Optional[str] = None
    changed_files: Optional[str] = None
    evaluator: Optional[str] = None
    artifact_report: Optional[str] = None   # G12: withheld/unwritable artifacts (safe metadata)

    def to_dict(self) -> dict:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "events": self.events,
            "final_diff": self.final_diff,
            "changed_files": self.changed_files,
            "evaluator": self.evaluator,
            "artifact_report": self.artifact_report,
        }


@dataclass
class CleanupRef:
    performed: bool = False
    report_ref: Optional[str] = None

    def to_dict(self) -> dict:
        return {"performed": self.performed, "report_ref": self.report_ref}


@dataclass
class RunResult:
    """Observed result of one run (protocol §7)."""

    run_id: str

    # timing
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: Optional[float] = None

    # process
    agent_exit_code: Optional[int] = None
    phase1_exit_code: Optional[int] = None   # C2 only; None otherwise
    phase2_exit_code: Optional[int] = None   # C2 only; None otherwise
    observed_session_id: Optional[str] = None
    session_continuity_verified: bool = False

    # status axes (protocol §6) — kept separate, never merged into a score
    agent_outcome: AgentOutcome = AgentOutcome.HARNESS_ERROR
    run_validity: RunValidity = RunValidity.VALID
    invalid_reason: Optional[str] = None
    interruption_reason: Optional[str] = None
    limit_interrupted: bool = False
    auth_failure: bool = False
    harness_failure: bool = False
    acceptance: Acceptance = Acceptance.NOT_RUN
    regression: Regression = Regression.NOT_RUN
    integrity: Integrity = Integrity.CLEAN
    c2_protocol: C2Protocol = C2Protocol.NOT_APPLICABLE
    evaluator_error: bool = False

    artifacts: ArtifactRefs = field(default_factory=ArtifactRefs)
    cleanup: CleanupRef = field(default_factory=CleanupRef)

    result_schema_version: str = RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "result_schema_version": self.result_schema_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "agent_exit_code": self.agent_exit_code,
            "phase1_exit_code": self.phase1_exit_code,
            "phase2_exit_code": self.phase2_exit_code,
            "observed_session_id": self.observed_session_id,
            "session_continuity_verified": self.session_continuity_verified,
            "agent_outcome": self.agent_outcome.value,
            "run_validity": self.run_validity.value,
            "invalid_reason": self.invalid_reason,
            "interruption_reason": self.interruption_reason,
            "limit_interrupted": self.limit_interrupted,
            "auth_failure": self.auth_failure,
            "harness_failure": self.harness_failure,
            "acceptance": self.acceptance.value,
            "regression": self.regression.value,
            "integrity": self.integrity.value,
            "c2_protocol": self.c2_protocol.value,
            "evaluator_error": self.evaluator_error,
            # G3: derived by the one canonical rule at write time -- never set independently.
            "analysis_eligibility": analysis_eligibility_dict(
                self.run_validity, self.agent_outcome, acceptance=self.acceptance,
                regression=self.regression, evaluator_error=self.evaluator_error),
            "artifacts": self.artifacts.to_dict(),
            "cleanup": self.cleanup.to_dict(),
        }

    def validate(self) -> list[str]:
        return validate_result_record(self.to_dict())

    def is_valid_document(self) -> bool:
        return not self.validate()


def validate_result_record(record: dict) -> list[str]:
    """Schema + cross-axis consistency (G3) for a result record, e.g. one read from result.json."""
    return (_schema.validate(record, load_schema("run-result.schema.json"))
            + check_status_consistency(record))


def audit_run_directory(run_dir, extra_markers=()) -> list[str]:
    """The canonical per-attempt finalization invariant (G12). Empty list = auditable.

    Checks that one attempt's results directory has a valid, consistent ``result.json`` and a
    ``manifest.json``; that every non-null artifact ref (and the cleanup report) exists; that no
    evidence the harness failed to store sits under a still-``valid`` record; that withheld
    placeholders are explained by ``artifact_report.json``; and that no file contains a secret
    marker. Problems are reported by file name only, never by content.
    """
    import json
    from pathlib import Path

    from .artifacts import CONTENT_WITHHELD, scan_for_secrets

    run_dir = Path(run_dir)
    problems: list[str] = []
    for required in ("result.json", "manifest.json", "cleanup.json"):
        if not (run_dir / required).is_file():
            problems.append(f"missing {required}")
    if (run_dir / "result.json").is_file():
        record = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        problems += [f"result.json: {e}" for e in validate_result_record(record)]
        refs = dict(record.get("artifacts") or {})
        refs["cleanup.report_ref"] = (record.get("cleanup") or {}).get("report_ref")
        for key, ref in refs.items():
            if ref and not (run_dir / ref).is_file():
                problems.append(f"artifact ref {key} -> {ref} missing")
        report_path = run_dir / "artifact_report.json"
        entries = (json.loads(report_path.read_text(encoding="utf-8"))["entries"]
                   if report_path.is_file() else [])
        if any(e["status"] == "write_failed" for e in entries) and record.get("run_validity") == "valid":
            problems.append("evidence could not be stored but the attempt is still valid")
        placeholders = [f.name for f in run_dir.iterdir() if f.is_file()
                        and CONTENT_WITHHELD in f.read_text(encoding="utf-8", errors="replace")
                        and f.name != "artifact_report.json"]
        if placeholders and not refs.get("artifact_report"):
            problems.append(f"withheld content without artifact_report: {sorted(placeholders)}")
    for f in sorted(run_dir.rglob("*")):
        if f.is_file() and scan_for_secrets(f.read_text(encoding="utf-8", errors="replace"), extra_markers):
            problems.append(f"secret marker persisted in {f.name}")
    return problems
