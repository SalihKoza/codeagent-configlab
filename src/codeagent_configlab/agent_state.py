"""Agent-start and agent-final state identity, start-relative delta and patch (G7).

The *pristine fixture baseline* (neutral commit, G6) and the *agent-visible start state* are
different things: the start state is the pristine tree plus the Candidate-2 seeded settings plus,
for C1/C2, the treatment ``CLAUDE.md``. The agent's delta is always computed against the start
state, so intentional harness material never looks like something the agent created.

Only documented runtime noise is excluded (:data:`STATE_IGNORED_DIRS`). ``.git`` is excluded from
the file snapshot and tracked separately through ``HEAD``; ``.claude/`` is *not* excluded.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .hashing import canonical_json_hash, sha256_bytes

STATE_IGNORED_DIRS = (".git", "__pycache__", ".pytest_cache")
MAX_INLINE_BYTES = 512 * 1024

# --- task-package generated outputs (pilot-readiness cleanup) -------------------------------
# A task package may declare build/runtime outputs (``package.json: generated_outputs``) that the
# agent's own commands legitimately create, e.g. ``dist/**`` and ``*.tsbuildinfo`` for a
# TypeScript task. Only two explicit forms exist -- no gitignore semantics:
#   "<dir>/**"  a directory at the working-copy root (plain name, no wildcards/nesting/dotfiles)
#   "*.<ext>"   a file-name suffix anywhere
# Anything that could hide a meaningful change (sources, tests, configs, instruction state) is
# rejected, and an instruction path is never treated as generated.
FORBIDDEN_GENERATED_DIRS = frozenset({"src", "lib", "test", "tests", "__tests__", "spec",
                                      ".claude", ".git", "node_modules"})
FORBIDDEN_GENERATED_EXTS = frozenset({"py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "mts", "cts",
                                      "json", "md", "toml", "yaml", "yml", "cfg", "ini", "txt",
                                      "lock", "sh"})
_PLAIN = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*$")


def validate_generated_patterns(patterns) -> list[str]:
    errors = []
    for p in patterns:
        if not isinstance(p, str):
            errors.append(f"{p!r}: not a string")
        elif p.endswith("/**") and p[:-3] and _PLAIN.match(p[:-3]) and not p.startswith("."):
            if p[:-3].lower() in FORBIDDEN_GENERATED_DIRS:
                errors.append(f"{p!r}: may hide source/test/instruction state")
        elif p.startswith("*.") and p[2:] and _PLAIN.match(p[2:]):
            ext = p[2:].lower().rsplit(".", 1)[-1]
            if p[2:].lower() in FORBIDDEN_GENERATED_EXTS or ext in FORBIDDEN_GENERATED_EXTS:
                errors.append(f"{p!r}: may hide source/config files")
        else:
            errors.append(f"{p!r}: only '<dir>/**' (root-level dir) or '*.<ext>' are allowed")
    return errors


def is_generated(rel: str, patterns) -> bool:
    """True if ``rel`` (posix, WC-relative) is a declared generated output. Never true for
    instruction state (CLAUDE.md, CLAUDE.local.md, anything under .claude/)."""
    from .treatment import is_instruction_path

    if not patterns or is_instruction_path(rel):
        return False
    first, name = rel.split("/", 1)[0], rel.rsplit("/", 1)[-1]
    for p in patterns:
        if p.endswith("/**") and "/" in rel and first == p[:-3]:
            return True
        if p.startswith("*.") and name.endswith(p[1:]) and name != p[1:]:
            return True
    return False


@dataclass(frozen=True)
class StateIdentity:
    tree_hash: str
    files: dict  # relative posix path -> sha256 (or "symlink:<target>")
    generated_ignore: tuple = ()

    def to_dict(self) -> dict:
        return {"tree_hash": self.tree_hash, "file_count": len(self.files),
                "ignored_dirs": list(STATE_IGNORED_DIRS),
                "generated_ignore": list(self.generated_ignore),
                "files": dict(sorted(self.files.items()))}


def take_snapshot(root: Path, generated=()) -> StateIdentity:
    """Files of the working copy minus runtime noise and the package's declared generated outputs."""
    from .orchestration import snapshot_tree

    generated = tuple(generated)
    files = {rel: h for rel, h in snapshot_tree(Path(root), ignore_dirs=STATE_IGNORED_DIRS).items()
             if not is_generated(rel, generated)}
    return StateIdentity(tree_hash=canonical_json_hash(dict(sorted(files.items()))), files=files,
                         generated_ignore=generated)


def delta(start: StateIdentity, final: StateIdentity) -> dict:
    """added / modified / deleted / renamed relative to the agent-start state."""
    a, b = start.files, final.files
    added = sorted(set(b) - set(a))
    deleted = sorted(set(a) - set(b))
    modified = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    renamed = []
    for old in list(deleted):
        match = next((new for new in added if b[new] == a[old]), None)
        if match is not None:
            renamed.append([old, match])
            deleted.remove(old)
            added.remove(match)
    return {"relative_to": "agent_start_state", "added": added, "modified": modified,
            "deleted": deleted, "renamed": renamed}


def _text(data: Optional[bytes]) -> Optional[list[str]]:
    if data is None or len(data) > MAX_INLINE_BYTES or b"\0" in data:
        return None
    try:
        return data.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def _final_bytes(root: Path, rel: str, digest: str) -> Optional[bytes]:
    if digest.startswith("symlink:"):
        return f"symlink -> {digest[8:]}\n".encode()
    try:
        return (root / rel).read_bytes()
    except OSError:
        return None


def unified_patch(start: StateIdentity, final: StateIdentity, changes: dict,
                  start_bytes: Callable[[str], Optional[bytes]], final_root: Path) -> str:
    """A human-reviewable patch of the agent's delta.

    ``start_bytes(rel)`` supplies the start content; it is only used if its hash equals the
    recorded start hash, otherwise the file is reported as "start content unavailable".
    """
    def start_content(rel):
        digest = start.files[rel]
        if digest.startswith("symlink:"):
            return f"symlink -> {digest[8:]}\n".encode()
        data = start_bytes(rel)
        return data if data is not None and sha256_bytes(data) == digest else None

    out: list[str] = []

    def emit(old_rel, new_rel, old_data, new_data, old_missing=False, new_missing=False):
        a_name = "/dev/null" if old_missing else f"a/{old_rel}"
        b_name = "/dev/null" if new_missing else f"b/{new_rel}"
        old_lines = [] if old_missing else _text(old_data)
        new_lines = [] if new_missing else _text(new_data)
        out.append(f"diff --configlab {a_name} {b_name}\n")
        if old_lines is None or new_lines is None:
            reason = "start content unavailable" if not old_missing and old_data is None else \
                "binary or oversized file"
            out.append(f"# {reason}; not inlined\n")
            return
        for line in difflib.unified_diff(old_lines, new_lines, a_name, b_name):
            out.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")

    for old, new in changes["renamed"]:
        out.append(f"diff --configlab a/{old} b/{new}\n# renamed, content unchanged\n")
    for rel in changes["added"]:
        emit(rel, rel, None, _final_bytes(final_root, rel, final.files[rel]), old_missing=True)
    for rel in changes["deleted"]:
        emit(rel, rel, start_content(rel), None, new_missing=True)
    for rel in changes["modified"]:
        emit(rel, rel, start_content(rel), _final_bytes(final_root, rel, final.files[rel]))
    return "".join(out)


def start_bytes_reader(pristine: Path, overrides: dict) -> Callable[[str], Optional[bytes]]:
    """Start content = ``overrides`` (seeds, treatment) else the pristine fixture file."""
    def read(rel: str) -> Optional[bytes]:
        if rel in overrides:
            return overrides[rel]
        try:
            return (Path(pristine) / rel).read_bytes()
        except OSError:
            return None
    return read


def capture_final_state(*, store, result, working_copy: Path, pristine: Path,
                        start_state: StateIdentity, expected_start: dict, treatment,
                        seeded: bool, configuration: str, baseline_commit,
                        generated=()) -> tuple:
    """Snapshot what the agent left, check the treatment-state invariant, and write
    ``final_state.json``, ``changed_files.json``, ``final.diff`` and ``treatment.json``.

    Called after the agent has ended and before any evaluator copy exists; reads the canonical
    working copy and never writes to it.
    """
    from .baseline import read_head
    from .treatment import TREATMENT_FILE, instruction_invariant, instruction_state
    from .workspace import SEED_CONTENT, SEEDED_FILES

    # G12: every write here may carry agent-controlled names/content -> write_safe (never raises;
    # withheld content is recorded in artifact_report.json, storage failures surface at finalize).
    final = take_snapshot(working_copy, generated)
    changes = delta(start_state, final)
    if store.write_safe("changed_files.json", changes)["status"] != "write_failed":
        result.artifacts.changed_files = store.ref("changed_files.json")

    overrides = {p: SEED_CONTENT for p in SEEDED_FILES} if seeded else {}
    if configuration in ("C1", "C2") and treatment is not None and treatment.claude_md is not None:
        overrides[TREATMENT_FILE] = treatment.claude_md
    patch = unified_patch(start_state, final, changes, start_bytes_reader(pristine, overrides),
                          Path(working_copy))
    diff = store.write_safe("final.diff", patch)
    if diff["status"] != "write_failed":
        result.artifacts.final_diff = store.ref("final.diff")

    head = read_head(Path(working_copy))
    record = final.to_dict()
    record.update({"start_tree_hash": start_state.tree_hash, "baseline_commit": baseline_commit,
                   "head_commit": head, "head_moved": head != baseline_commit if baseline_commit else None,
                   # a boolean only (pre-G12 this held the scanner message, i.e. the marker)
                   "final_diff_withheld": bool(diff["content_withheld"])})
    store.write_safe("final_state.json", record)

    invariant = instruction_invariant(expected_start, instruction_state(start_state.files),
                                      instruction_state(final.files))
    invariant["configuration"] = configuration
    store.write_safe("treatment.json", invariant)
    return final, invariant
