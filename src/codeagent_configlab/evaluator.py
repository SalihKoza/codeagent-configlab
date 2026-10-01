"""Evaluator boundary (protocol §6) + a trivial smoke evaluator.

The evaluator is independent of the agent: it runs only after the agent process has ended, on a
**copy** of the final working-copy snapshot (never in place), restoring each task's protected
paths and adding hidden material — all of which lives outside the agent-visible sandbox. It
returns structured acceptance/regression/integrity verdicts, and distinguishes an *evaluator
error* (the check could not run) from a legitimate *task failure* (the check ran and failed).

This module holds the abstraction and the HARNESS_SMOKE_ONLY :class:`SmokeEvaluator`. The
production evaluator for real tasks is :mod:`codeagent_configlab.task_evaluator`.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

from .status import Acceptance, Regression, Integrity


@dataclass
class EvaluationResult:
    acceptance: Acceptance
    regression: Regression
    integrity: Integrity = Integrity.CLEAN
    evaluator_error: bool = False
    detail: str = ""
    # Real task evaluator detail (G5); empty for the smoke evaluator.
    checks: list = field(default_factory=list)        # per-check kind/name/status/exit/output tail
    restoration: list = field(default_factory=list)   # protected-path restore record
    injected: list = field(default_factory=list)      # hidden files injected (relative names only)
    sandbox: dict = field(default_factory=dict)       # G5s evaluator-sandbox provenance (no secrets)

    def to_dict(self) -> dict:
        return {
            "acceptance": self.acceptance.value,
            "regression": self.regression.value,
            "integrity": self.integrity.value,
            "evaluator_error": self.evaluator_error,
            "detail": self.detail,
            "checks": self.checks,
            "restoration": self.restoration,
            "injected": self.injected,
            "sandbox": self.sandbox,
        }


class Evaluator(Protocol):
    """An evaluator consumes a final working-copy path and returns an EvaluationResult.

    Implementations MUST NOT modify the given path; they copy it first.
    """

    def evaluate(self, final_working_copy: Path) -> EvaluationResult: ...


def _copy_for_evaluation(final_working_copy: Path) -> Path:
    """Copy the final WC into a throwaway temp dir so evaluation never touches agent state."""
    tmp = Path(tempfile.mkdtemp(prefix="cclab-eval-"))
    dest = tmp / "wc"
    shutil.copytree(final_working_copy, dest, symlinks=True)
    return dest


@dataclass
class SmokeEvaluator:
    """A trivial, non-secret evaluator for the harness smoke fixture.

    Acceptance: ``calc.py`` defines ``multiply`` (the smoke "feature").
    Regression: ``calc.py`` still defines ``add`` (nothing pre-existing was broken).
    Both are computed on a *copy* of the final WC. If ``calc.py`` is missing/unreadable the
    result is an evaluator error, NOT a task failure.
    """

    target_file: str = "calc.py"
    acceptance_symbol: str = "def multiply"
    regression_symbol: str = "def add"

    def evaluate(self, final_working_copy: Path) -> EvaluationResult:
        work = _copy_for_evaluation(Path(final_working_copy))
        try:
            target = work / self.target_file
            if not target.exists():
                return EvaluationResult(
                    acceptance=Acceptance.ERROR,
                    regression=Regression.ERROR,
                    evaluator_error=True,
                    detail=f"target file {self.target_file!r} missing",
                )
            try:
                text = target.read_text(encoding="utf-8")
            except OSError as exc:
                return EvaluationResult(
                    acceptance=Acceptance.ERROR,
                    regression=Regression.ERROR,
                    evaluator_error=True,
                    detail=f"could not read {self.target_file!r}: {exc}",
                )
            acceptance = Acceptance.PASS if self.acceptance_symbol in text else Acceptance.FAIL
            regression = Regression.PASS if self.regression_symbol in text else Regression.FAIL
            return EvaluationResult(
                acceptance=acceptance,
                regression=regression,
                integrity=Integrity.CLEAN,
                evaluator_error=False,
                detail="smoke evaluation on a copy of the final working copy",
            )
        finally:
            shutil.rmtree(work.parent, ignore_errors=True)
