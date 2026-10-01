"""Clean disposable working-copy primitive (protocol §4).

Creates a fresh working copy from a pristine fixture for exactly one run, at an **opaque** path
that encodes nothing about task/config/repetition. Guarantees the harness must uphold:

* the pristine source is never modified (copy only);
* one fresh copy per run, never reused, no prior-run modifications or artifacts inside it;
* the fixture carries no hidden tests / reference solution / evaluator (that is the fixture
  author's responsibility; this primitive additionally refuses obvious leakage names);
* the baseline state is hashable (:func:`~codeagent_configlab.hashing.tree_hash`);
* no ancestor directory contains a ``CLAUDE.md``/instruction file (checked before a run).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .hashing import tree_hash
from .ids import new_workspace_token

# Instruction-file names whose presence in an ancestor directory would contaminate a run
# (protocol §4/§8). Checked from the working copy up to the filesystem root.
INSTRUCTION_FILE_NAMES = ("CLAUDE.md", "CLAUDE.local.md")

# Names that must never appear inside a working copy for it to be a clean agent view
# (protocol §5). This is a defensive check on the fixture, not a substitute for authoring it
# correctly.
FORBIDDEN_WC_NAMES = ("reference_solution", "hidden_tests", "evaluator", ".cclab-token")


# Candidate-2 runtime seeding: exact files and exact content. Only these, with exactly this
# content, are treated as harness material rather than repository content.
SEED_CONTENT = b"{}\n"
SEEDED_FILES = (".claude/settings.json", ".claude/settings.local.json")
# sandbox-runtime always write-protects <cwd>/.claude/commands and <cwd>/.claude/agents and, when
# they are missing, places a mount placeholder there. With <wc>/.claude read-only (G11) the
# placeholder cannot be created and the sandbox refuses to start, so both exist as empty dirs.
SEEDED_DIRS = (".claude/commands", ".claude/agents")


@dataclass(frozen=True)
class WorkingCopy:
    path: Path
    token: str
    baseline_hash: str
    baseline_commit: Optional[str] = None   # the neutral pristine commit (G6), if created


def check_ancestor_instructions(start: Path) -> list[Path]:
    """Return any instruction files found in ``start`` or an ancestor directory.

    An empty list means the ancestor chain is clean. A non-empty list is a preflight failure
    (protocol §4: the harness refuses to start otherwise).
    """
    found: list[Path] = []
    p = start.resolve()
    for directory in [p, *p.parents]:
        for name in INSTRUCTION_FILE_NAMES:
            candidate = directory / name
            if candidate.exists():
                found.append(candidate)
    return found


def _assert_clean_fixture(pristine: Path) -> None:
    if (pristine / ".git").exists():
        # Fixture history could carry reference solutions or authoring notes; the neutral
        # baseline is always created fresh by the harness (G6).
        raise ValueError(f"pristine fixture must not contain a .git directory: {pristine}")
    for name in FORBIDDEN_WC_NAMES:
        if (pristine / name).exists():
            raise ValueError(f"pristine fixture must not contain {name!r}: {pristine / name}")


def seed_wc_settings(working_copy: Path) -> list[Path]:
    """Seed empty ``.claude/settings.json`` + ``settings.local.json`` in the working copy.

    Candidate-2 operating requirement: without these files Claude's Bash-tool bwrap cannot
    stage its settings mount and every Bash command fails. They are empty (``{}``) and, as
    Candidate 2 proved, cannot weaken protection (operator posture wins; ``--setting-sources ""``
    excludes them). Returns the created paths.
    """
    claude_dir = working_copy / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for name in ("settings.json", "settings.local.json"):
        f = claude_dir / name
        f.write_bytes(SEED_CONTENT)
        created.append(f)
    for rel in SEEDED_DIRS:
        d = working_copy / rel
        d.mkdir(parents=True, exist_ok=True)
        created.append(d)
    return created


def make_working_copy(
    pristine: Path | str, runs_root: Path | str, *, seed_settings: bool = True,
    token: Optional[str] = None, git_baseline: bool = False,
) -> WorkingCopy:
    """Copy a pristine fixture to a fresh opaque directory under ``runs_root``.

    The destination directory name is an opaque token. Pass ``token`` to use the manifest's
    ``workspace_token`` so the on-disk path matches the recorded provenance; omit it to mint a
    fresh one (:func:`new_workspace_token`). Either way the name leaks no experimental structure.
    The pristine source is copied from and never written back. Refuses to overwrite an existing
    token dir.

    ``git_baseline=True`` turns the copy into a one-commit repository of the pristine fixture
    (:mod:`codeagent_configlab.baseline`) *before* runtime seeding, so seeds and treatment are
    never part of the neutral history.
    """
    pristine = Path(pristine)
    runs_root = Path(runs_root)
    if not pristine.is_dir():
        raise FileNotFoundError(f"pristine fixture not found: {pristine}")
    _assert_clean_fixture(pristine)

    runs_root.mkdir(parents=True, exist_ok=True)
    token = token or new_workspace_token()
    if not token or "/" in token or "\\" in token or token in (".", ".."):
        raise ValueError(f"invalid workspace token: {token!r}")
    dest = runs_root / token
    if dest.exists():  # astronomically unlikely; refuse rather than clobber
        raise FileExistsError(f"workspace token collision: {dest}")

    shutil.copytree(pristine, dest, symlinks=True)
    commit = None
    if git_baseline:
        from .baseline import create_baseline

        commit = create_baseline(dest)
    if seed_settings:
        seed_wc_settings(dest)
    baseline = tree_hash(dest)
    return WorkingCopy(path=dest, token=token, baseline_hash=baseline, baseline_commit=commit)


def changed_files(pristine: Path | str, working_copy: Path | str,
                  expected_extra: Optional[dict[str, str]] = None) -> dict:
    """Return added / modified / deleted file lists comparing a WC to its pristine fixture.

    Compared against the out-of-sandbox pristine snapshot (protocol §14), ignoring generated
    caches and ``.git`` per :func:`tree_hash`'s ignore list. Only the two Candidate-2 seeded
    settings files are excluded, and only while they still hold the exact seed content; any other
    ``.claude/`` material is reported like any other file.

    ``expected_extra`` (relative path -> SHA-256) extends the baseline with the intentional
    treatment files (the C1/C2 ``CLAUDE.md``), so an unchanged treatment is not "added" while an
    agent edit or deletion of it is reported as modified / deleted.
    """
    from .hashing import DEFAULT_IGNORE_DIRS, sha256_file

    def _index(root: Path) -> dict[str, str]:
        idx: dict[str, str] = {}
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(root)
            parts = set(rel.parts)
            if parts & set(DEFAULT_IGNORE_DIRS):
                continue
            key = rel.as_posix()
            if key in SEEDED_FILES and f.read_bytes() == SEED_CONTENT:
                continue  # exact Candidate-2 seed, not repository content
            idx[key] = sha256_file(f)
        return idx

    a = _index(Path(pristine))
    a.update(expected_extra or {})
    b = _index(Path(working_copy))
    added = sorted(set(b) - set(a))
    deleted = sorted(set(a) - set(b))
    modified = sorted(k for k in (set(a) & set(b)) if a[k] != b[k])
    return {"added": added, "modified": modified, "deleted": deleted}


def write_changed_files_report(pristine: Path | str, working_copy: Path | str, out: Path) -> Path:
    out.write_text(json.dumps(changed_files(pristine, working_copy), indent=2), encoding="utf-8")
    return out
