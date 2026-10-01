"""The run manifest — the immutable specification of one experimental run.

A run is ``(task, configuration, repetition)`` executed once (protocol §2). The manifest holds
*planned inputs only*; observed outputs live in :mod:`codeagent_configlab.result`. Nothing here
is a secret, and runtime results never write back into a manifest.

Two absence semantics (see :mod:`codeagent_configlab.sentinels`):

* ``OPEN`` (string) — decision not yet frozen (model pin, effort level, timeout). Defaults live
  here as OPEN so a plausible value cannot silently become the frozen default.
* ``None`` — not applicable to this configuration (e.g. planning fields on C0/C1).

Beyond the structural JSON-Schema check, :meth:`RunManifest.validate` enforces
configuration-conditional rules that the schema subset cannot express.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Union

from . import SCHEMA_VERSION
from ._schemas import load_schema
from . import schema as _schema
from .sentinels import OPEN

# Environment version pins (from setup/common.sh, verified during setup). Recorded per run so
# version drift is a measured confound (protocol §3.1, risk R2).
CLAUDE_CODE_VERSION = "2.1.263"
NODE_VERSION = "22.23.2"
NPM_VERSION = "10.9.8"
SANDBOX_RUNTIME_VERSION = "0.0.77"

SERIES_FIELDS = ("namespace", "series_id", "series_spec_hash", "cell_id", "attempt_ordinal",
                 "attempt_kind", "original_attempt_id", "predecessor_attempt_id",
                 "replacement_reason")

# Effort levels the installed Claude Code CLI's --effort flag accepts (`claude --help`).
_VALID_EFFORT_LEVELS = frozenset({"low", "medium", "high", "xhigh", "max"})

OpenOrStr = Union[str]  # documentation alias: either the OPEN sentinel or a real string
OpenOrNumber = Union[str, float, int]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class RunManifest:
    """Immutable specification of one run (protocol §6/§7).

    Frozen dataclass: once built, a manifest cannot be mutated in place — the experimental
    specification is not allowed to drift during a run.
    """

    run_id: str
    task_id: str
    task_version_hash: str
    language: str                      # "python" | "typescript"
    task_category: str                 # "bugfix" | "feature" | "refactor"
    configuration: str                 # "C0" | "C1" | "C2"
    repetition: int
    workspace_token: str
    settings_policy_hash: str
    security_policy_hash: str
    task_statement_hash: str
    implementation_tool_set: tuple[str, ...]

    # Configuration-conditional / OPEN fields with explicit defaults.
    planning_tool_set: Optional[tuple[str, ...]] = None      # None for C0/C1; tuple for C2
    claude_md_hash: Optional[str] = None                     # None for C0; hash for C1/C2
    planning_wrapper_hash: Optional[str] = None              # None unless C2
    approval_message_hash: Optional[str] = None              # None unless C2
    order_position: Optional[int] = None                     # None until the order is assigned
    order_seed_ref: Optional[str] = None                     # None until the order is assigned
    model_request: str = OPEN                                # OPEN until frozen (O5)
    effort_request: str = OPEN                               # OPEN until frozen (pilot execution spec)
    timeout_seconds: Union[str, float] = OPEN                # OPEN until frozen (O12)
    permission_mode: str = "bypassPermissions"

    # Provenance version pins.
    claude_code_version: str = CLAUDE_CODE_VERSION
    node_version: str = NODE_VERSION
    npm_version: str = NPM_VERSION
    sandbox_runtime_version: str = SANDBOX_RUNTIME_VERSION

    created_at: str = field(default_factory=_utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    # G10 series provenance (additive within v0; all None outside a series, e.g. the smoke).
    # run_id is the opaque ATTEMPT id; cell_id names the planned task x config x repetition cell.
    namespace: Optional[str] = None                 # "PILOT" | "HARNESS_SMOKE_ONLY" | "FINAL"
    series_id: Optional[str] = None                 # pilot version, e.g. "pilot-v1"
    series_spec_hash: Optional[str] = None
    cell_id: Optional[str] = None
    attempt_ordinal: Optional[int] = None           # 1 = original, 2 = the (at most one) replacement
    attempt_kind: Optional[str] = None              # "original" | "replacement"
    original_attempt_id: Optional[str] = None
    predecessor_attempt_id: Optional[str] = None
    replacement_reason: Optional[str] = None

    # ------------------------------------------------------------------ serialize --
    def to_dict(self) -> dict:
        """Serialize to a plain JSON-ready dict (tuples become lists)."""
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "task_version_hash": self.task_version_hash,
            "language": self.language,
            "task_category": self.task_category,
            "configuration": self.configuration,
            "repetition": self.repetition,
            "order_position": self.order_position,
            "order_seed_ref": self.order_seed_ref,
            "workspace_token": self.workspace_token,
            "claude_code_version": self.claude_code_version,
            "node_version": self.node_version,
            "npm_version": self.npm_version,
            "sandbox_runtime_version": self.sandbox_runtime_version,
            "model_request": self.model_request,
            "effort_request": self.effort_request,
            "permission_mode": self.permission_mode,
            "implementation_tool_set": list(self.implementation_tool_set),
            "planning_tool_set": (
                None if self.planning_tool_set is None else list(self.planning_tool_set)
            ),
            "settings_policy_hash": self.settings_policy_hash,
            "security_policy_hash": self.security_policy_hash,
            "task_statement_hash": self.task_statement_hash,
            "claude_md_hash": self.claude_md_hash,
            "planning_wrapper_hash": self.planning_wrapper_hash,
            "approval_message_hash": self.approval_message_hash,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
            **({k: getattr(self, k) for k in SERIES_FIELDS} if self.namespace is not None else {}),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RunManifest":
        def _tuple_or_none(v):
            return None if v is None else tuple(v)

        return cls(
            run_id=data["run_id"],
            task_id=data["task_id"],
            task_version_hash=data["task_version_hash"],
            language=data["language"],
            task_category=data["task_category"],
            configuration=data["configuration"],
            repetition=data["repetition"],
            workspace_token=data["workspace_token"],
            settings_policy_hash=data["settings_policy_hash"],
            security_policy_hash=data["security_policy_hash"],
            task_statement_hash=data["task_statement_hash"],
            implementation_tool_set=tuple(data["implementation_tool_set"]),
            planning_tool_set=_tuple_or_none(data["planning_tool_set"]),
            claude_md_hash=data["claude_md_hash"],
            planning_wrapper_hash=data["planning_wrapper_hash"],
            approval_message_hash=data["approval_message_hash"],
            order_position=data["order_position"],
            order_seed_ref=data["order_seed_ref"],
            model_request=data["model_request"],
            effort_request=data["effort_request"],
            timeout_seconds=data["timeout_seconds"],
            permission_mode=data["permission_mode"],
            claude_code_version=data["claude_code_version"],
            node_version=data["node_version"],
            npm_version=data["npm_version"],
            sandbox_runtime_version=data["sandbox_runtime_version"],
            created_at=data["created_at"],
            schema_version=data["schema_version"],
            **{k: data.get(k) for k in SERIES_FIELDS},
        )

    # ------------------------------------------------------------------ validate --
    def validate(self) -> list[str]:
        """Structural (JSON-Schema) + semantic (configuration-conditional) validation.

        Returns a list of error strings (empty == valid). Semantic rules the schema subset
        cannot express:

        * C0 has no treatment CLAUDE.md -> ``claude_md_hash`` MUST be null; C1/C2 MUST have it.
        * Only C2 has a planning phase -> ``planning_tool_set``, ``planning_wrapper_hash`` and
          ``approval_message_hash`` MUST be non-null for C2 and null for C0/C1.
        """
        data = self.to_dict()
        errors = _schema.validate(data, load_schema("run-manifest.schema.json"))

        # A provider default is not a frozen model id (it can drift over time): reject the literal
        # "Default" (case-insensitive) rather than silently accepting it as a plausible model id.
        if self.model_request != OPEN and self.model_request.strip().lower() == "default":
            errors.append("model_request must not be the literal 'Default' (a provider default is "
                          "not a frozen model id); pass the explicit model id instead")
        if self.effort_request != OPEN and self.effort_request not in _VALID_EFFORT_LEVELS:
            errors.append(f"effort_request must be OPEN or one of {sorted(_VALID_EFFORT_LEVELS)}, "
                          f"got {self.effort_request!r}")

        cfg = self.configuration
        if cfg == "C0" and self.claude_md_hash is not None:
            errors.append("C0 run must have claude_md_hash == null (no treatment CLAUDE.md)")
        if cfg in ("C1", "C2") and self.claude_md_hash is None:
            errors.append(f"{cfg} run must have a non-null claude_md_hash")

        c2_only = {
            "planning_tool_set": self.planning_tool_set,
            "planning_wrapper_hash": self.planning_wrapper_hash,
            "approval_message_hash": self.approval_message_hash,
        }
        for name, value in c2_only.items():
            if cfg == "C2" and value is None:
                errors.append(f"C2 run must have a non-null {name}")
            if cfg in ("C0", "C1") and value is not None:
                errors.append(f"{cfg} run must have {name} == null (no planning phase)")

        return errors

    def is_valid(self) -> bool:
        return not self.validate()
