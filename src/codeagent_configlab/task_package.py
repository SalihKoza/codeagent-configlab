"""Task-package loader (G10), following ``docs/PILOT_TASK_STANDARD.md`` §2/§11/§13.

A package directory lives under the harness root (``denyRead`` in every agent sandbox) and holds a
trusted ``package.json``::

    {"task_id": "P-PY-01", "language": "python", "task_category": "bugfix",
     "statement": "statement.md", "pristine": "pristine", "hidden": "hidden",
     "reference": "reference",
     "evaluator": {"acceptance": [{"name": ..., "argv": [...], "timeout_seconds": 120,
                                   "error_codes": []}],
                   "regression": [...], "structural": [...],
                   "protected_paths": [...], "hidden_dest": "_hidden_tests", "env": {}},
     "generated_outputs": ["dist/**", "*.tsbuildinfo"],        # optional; default []
     "validity_gate": {"status": "PASS", "task_version_hash": "<sha256>", "evidence_ref": "..."}}

``generated_outputs`` declares build/runtime outputs the agent's own commands legitimately create
(``agent_state.validate_generated_patterns``: ``<dir>/**`` or ``*.<ext>`` only; sources, tests,
configs and instruction state can never be declared). They are excluded from the start/final
state, changed files and diff, removed from the evaluator copy before any check, and part of the
task version identity. C2 phase 1 stays strict (any new file there is a write).

Treatment material (CLAUDE.md, C2 wrapper/approval) is *not* part of a task package (§2); it is
authored once per series. This module does not run the validity gate; it only refuses a package
whose recorded gate result is not ``PASS`` for exactly the package bytes on disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .hashing import canonical_json_hash, sha256_bytes, tree_hash
from .task_evaluator import CheckSpec, TaskEvaluatorSpec

PACKAGE_FILE = "package.json"
GATE_PASS = "PASS"
# node_modules is part of a TypeScript pristine fixture (PILOT_PLAN §5/§15) and must be hashed.
_HASH_IGNORE = (".git", "__pycache__")


def _checks(items) -> tuple[CheckSpec, ...]:
    return tuple(CheckSpec(name=c["name"], argv=tuple(c["argv"]),
                           timeout_seconds=float(c.get("timeout_seconds", 120.0)),
                           error_codes=tuple(c.get("error_codes", ())))
                 for c in items or ())


@dataclass(frozen=True)
class TaskPackage:
    root: Path
    meta: dict

    @classmethod
    def load(cls, root) -> "TaskPackage":
        from .agent_state import validate_generated_patterns

        root = Path(root)
        pkg = cls(root=root, meta=json.loads((root / PACKAGE_FILE).read_text(encoding="utf-8")))
        errors = validate_generated_patterns(pkg.generated_outputs)
        if errors:
            raise ValueError(f"{pkg.task_id}: invalid generated_outputs: {errors}")
        return pkg

    @property
    def generated_outputs(self) -> tuple[str, ...]:
        return tuple(self.meta.get("generated_outputs", ()))

    # ---------------------------------------------------------------- parts --
    @property
    def task_id(self) -> str:
        return self.meta["task_id"]

    @property
    def language(self) -> str:
        return self.meta["language"]

    @property
    def task_category(self) -> str:
        return self.meta["task_category"]

    @property
    def pristine(self) -> Path:
        return self.root / self.meta["pristine"]

    @property
    def hidden(self) -> Optional[Path]:
        return self.root / self.meta["hidden"] if self.meta.get("hidden") else None

    def statement_bytes(self) -> bytes:
        return (self.root / self.meta["statement"]).read_bytes()

    def statement(self) -> str:
        return self.statement_bytes().decode("utf-8")

    @property
    def statement_hash(self) -> str:
        # identical to hashing.sha256_text(statement) used for manifest.task_statement_hash
        return sha256_bytes(self.statement_bytes())

    def evaluator_config(self) -> dict:
        return self.meta["evaluator"]

    def evaluator_spec(self) -> TaskEvaluatorSpec:
        ev = self.evaluator_config()
        return TaskEvaluatorSpec(
            pristine=self.pristine, hidden_dir=self.hidden,
            acceptance=_checks(ev.get("acceptance")), regression=_checks(ev.get("regression")),
            structural=_checks(ev.get("structural")),
            protected_paths=tuple(ev.get("protected_paths", ())),
            hidden_dest=ev.get("hidden_dest", "_hidden_tests"),
            env=tuple(sorted(dict(ev.get("env", {})).items())),
            generated_outputs=self.generated_outputs)

    def evaluator_identity(self) -> str:
        from .evaluator_sandbox import EVALUATOR_SANDBOX_VERSION

        return canonical_json_hash({"evaluator": self.evaluator_config(),
                                    "generated_outputs": list(self.generated_outputs),
                                    "sandbox_version": EVALUATOR_SANDBOX_VERSION})

    # ------------------------------------------------------------- identity --
    def version_hash(self) -> str:
        """Task version identity (§13): statement bytes, fixture tree, hidden tests, evaluator
        configuration and reference solution. Any change -> a new version -> a new gate."""
        parts = {"task_id": self.task_id, "language": self.language,
                 "task_category": self.task_category,
                 "statement": self.statement_hash,
                 "pristine": tree_hash(self.pristine, ignore_dirs=_HASH_IGNORE),
                 "hidden": tree_hash(self.hidden, ignore_dirs=_HASH_IGNORE) if self.hidden else None,
                 "evaluator": self.evaluator_config(),
                 "generated_outputs": list(self.generated_outputs)}
        ref = self.meta.get("reference")
        parts["reference"] = (tree_hash(self.root / ref, ignore_dirs=_HASH_IGNORE)
                              if ref and (self.root / ref).is_dir() else None)
        return canonical_json_hash(parts)

    def gate_errors(self) -> list[str]:
        """Empty only if the recorded validity gate is PASS for exactly these package bytes."""
        gate = self.meta.get("validity_gate") or {}
        errors = []
        if gate.get("status") != GATE_PASS:
            errors.append(f"{self.task_id}: validity gate status is {gate.get('status')!r}, not PASS")
        actual = self.version_hash()
        if gate.get("task_version_hash") != actual:
            errors.append(f"{self.task_id}: package changed since its validity gate "
                          f"(recorded {gate.get('task_version_hash')}, now {actual})")
        from .agent_state import is_generated
        from .orchestration import snapshot_tree

        shipped = [rel for rel in snapshot_tree(self.pristine, ignore_dirs=_HASH_IGNORE)
                   if is_generated(rel, self.generated_outputs)]
        if shipped:
            errors.append(f"{self.task_id}: pristine fixture already contains declared generated "
                          f"outputs {sorted(shipped)[:5]} (their changes would be hidden)")
        return errors
