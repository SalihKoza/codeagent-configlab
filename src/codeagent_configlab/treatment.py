"""Treatment inputs for C1/C2 and their provenance (protocol §3.2, §3.3, §8).

The treatment is operator-controlled, frozen material that is **not** part of the task:

* ``claude_md`` — the benchmark ``CLAUDE.md`` bytes (C1 and C2, byte-identical);
* ``planning_wrapper`` — the fixed C2 phase-1 text; it embeds the unmodified task statement at
  :data:`TASK_STATEMENT_SLOT`;
* ``approval_message`` — the fixed C2 continuation text sent regardless of the plan.

No production wording lives in code. The texts are supplied by the operator (e.g. with
:meth:`Treatment.from_files`) and checked against the hashes frozen in the manifest. The
*expected* working-copy state always comes from the manifest, never from the supplied treatment,
so a wrong treatment source is caught before the agent starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .hashing import sha256_bytes, sha256_text

TASK_STATEMENT_SLOT = "{{TASK_STATEMENT}}"
TREATMENT_FILE = "CLAUDE.md"   # the only treatment file; materialized at the working-copy root


@dataclass(frozen=True)
class Treatment:
    claude_md: Optional[bytes] = None
    planning_wrapper: Optional[str] = None
    approval_message: Optional[str] = None

    @classmethod
    def from_files(cls, claude_md: Optional[Path] = None, planning_wrapper: Optional[Path] = None,
                   approval_message: Optional[Path] = None) -> "Treatment":
        return cls(
            claude_md=Path(claude_md).read_bytes() if claude_md else None,
            planning_wrapper=Path(planning_wrapper).read_text(encoding="utf-8") if planning_wrapper else None,
            approval_message=Path(approval_message).read_text(encoding="utf-8") if approval_message else None,
        )

    @property
    def claude_md_hash(self) -> Optional[str]:
        return sha256_bytes(self.claude_md) if self.claude_md is not None else None

    @property
    def planning_wrapper_hash(self) -> Optional[str]:
        return sha256_text(self.planning_wrapper) if self.planning_wrapper is not None else None

    @property
    def approval_message_hash(self) -> Optional[str]:
        return sha256_text(self.approval_message) if self.approval_message is not None else None

    def render_planning_prompt(self, task_statement: str) -> str:
        """The phase-1 input: the wrapper with the task statement inserted unmodified."""
        if self.planning_wrapper is None:
            raise ValueError("C2 requires a planning wrapper")
        if self.planning_wrapper.count(TASK_STATEMENT_SLOT) != 1:
            raise ValueError(f"planning wrapper must contain {TASK_STATEMENT_SLOT} exactly once")
        return self.planning_wrapper.replace(TASK_STATEMENT_SLOT, task_statement)


def expected_treatment_files(manifest) -> dict[str, str]:
    """Root instruction files the working copy must contain, from the frozen manifest."""
    if manifest.configuration in ("C1", "C2"):
        return {TREATMENT_FILE: manifest.claude_md_hash}
    return {}


def materialize_treatment(working_copy: Path, configuration: str, treatment: Optional[Treatment]) -> None:
    """Write the C1/C2 ``CLAUDE.md`` at the working-copy root. Never touches C0.

    A missing treatment is not raised here: preflight reports it (the run is not started).
    """
    if configuration not in ("C1", "C2") or treatment is None or treatment.claude_md is None:
        return
    target = Path(working_copy) / TREATMENT_FILE
    if target.exists():
        raise FileExistsError(f"treatment target already exists (fixture not clean?): {target}")
    target.write_bytes(treatment.claude_md)


def treatment_provenance_errors(manifest, treatment: Optional[Treatment],
                                task_statement: Optional[str]) -> list[str]:
    """Mismatches between the supplied treatment/statement and the frozen manifest hashes."""
    errors: list[str] = []
    config = manifest.configuration
    if task_statement is not None and sha256_text(task_statement) != manifest.task_statement_hash:
        errors.append("task statement bytes do not match manifest.task_statement_hash")
    if config == "C0":
        if treatment is not None and any(
            v is not None for v in (treatment.claude_md, treatment.planning_wrapper, treatment.approval_message)
        ):
            errors.append("C0 must not receive treatment material")
        return errors
    if treatment is None or treatment.claude_md is None:
        errors.append(f"{config} requires the frozen CLAUDE.md treatment")
    elif treatment.claude_md_hash != manifest.claude_md_hash:
        errors.append("CLAUDE.md treatment does not match manifest.claude_md_hash")
    if config == "C1":
        if treatment is not None and (treatment.planning_wrapper or treatment.approval_message):
            errors.append("C1 must not receive C2 planning material")
        return errors
    # C2
    if treatment is None or treatment.planning_wrapper is None:
        errors.append("C2 requires the frozen planning wrapper")
    elif treatment.planning_wrapper_hash != manifest.planning_wrapper_hash:
        errors.append("planning wrapper does not match manifest.planning_wrapper_hash")
    elif treatment.planning_wrapper.count(TASK_STATEMENT_SLOT) != 1:
        errors.append(f"planning wrapper must contain {TASK_STATEMENT_SLOT} exactly once")
    if treatment is None or treatment.approval_message is None:
        errors.append("C2 requires the frozen approval message")
    elif treatment.approval_message_hash != manifest.approval_message_hash:
        errors.append("approval message does not match manifest.approval_message_hash")
    if task_statement is None:
        errors.append("C2 requires the task statement to render the planning wrapper")
    return errors


# --- treatment-state invariant --------------------------------------------------------------
# Instruction material that Claude Code 2.1.263's memory loader can pick up from a repository
# once project/local setting sources are enabled (root/nested CLAUDE.md, CLAUDE.local.md,
# .claude/CLAUDE.md, .claude/rules/**), plus the rest of any .claude/ tree (settings, skills,
# agents, commands: relevance UNCLEAR, so fail closed). See docs/PILOT_PLAN.md (G11).
INSTRUCTION_BASENAMES = ("CLAUDE.md", "CLAUDE.local.md")

# What Claude Code 2.1.263 actually reads from the working copy under the G11 loader
# (``--setting-sources ""`` + ``--add-dir <wc>`` + CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1),
# from static analysis of the installed binary. All of it is covered by the fail-closed
# instruction state below; everything under .claude/ is additionally write-protected at run time.
EFFECTIVE_INSTRUCTION_SOURCES = {
    "CLAUDE.md": "instruction (Project memory via --add-dir) -- the C1/C2 treatment",
    ".claude/CLAUDE.md": "instruction (Project memory via --add-dir)",
    ".claude/rules/**": "instruction (Project rules via --add-dir)",
    ".claude/agents/**": "agent definitions discovered in --add-dir directories",
    ".claude/skills/**": "skills discovered in --add-dir directories (unclear; fail closed)",
    ".claude/settings.json": "configuration: enabledPlugins / extraKnownMarketplaces only",
    ".claude/settings.local.json": "configuration: enabledPlugins / extraKnownMarketplaces only",
    "CLAUDE.local.md": "ignored (localSettings disabled)",
    "**/CLAUDE.md (nested)": "ignored (nested memory gated by projectSettings)",
}


def is_instruction_path(rel: str) -> bool:
    parts = rel.split("/")
    return parts[-1] in INSTRUCTION_BASENAMES or ".claude" in parts[:-1]


def instruction_state(files: dict) -> dict:
    """The instruction-relevant subset of a snapshot (relative path -> hash)."""
    return {k: v for k, v in sorted(files.items()) if is_instruction_path(k)}


def expected_start_instruction_state(expected_treatment: dict, seeded: bool) -> dict:
    """What the agent must see at start: the frozen treatment plus the exact runtime seeds."""
    from .workspace import SEED_CONTENT, SEEDED_FILES

    state = dict(expected_treatment)
    if seeded:
        state.update({p: sha256_bytes(SEED_CONTENT) for p in SEEDED_FILES})
    return dict(sorted(state.items()))


def instruction_invariant(expected_start: dict, start: dict, final: dict) -> dict:
    """Start must equal the expected treatment state; final must equal start. Nothing restored."""
    violations = []
    for p in sorted(set(expected_start) | set(start)):
        if expected_start.get(p) != start.get(p):
            violations.append(f"start: {p} is {'missing' if p not in start else 'unexpected or altered'}")
    for p in sorted(set(start) | set(final)):
        if p not in final:
            violations.append(f"deleted {p}")
        elif p not in start:
            violations.append(f"created {p}")
        elif start[p] != final[p]:
            violations.append(f"modified {p}")
    return {"ok": not violations, "violations": violations,
            "expected_start": expected_start, "start": start, "final": final}
