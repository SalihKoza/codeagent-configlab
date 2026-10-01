"""Neutral, deterministic pristine git baseline (G6, protocol §4).

Every working copy is a git repository holding exactly one commit of the pristine task fixture.
The commit is built with fixed, neutral metadata and with host git configuration isolated, so the
same fixture always yields the same commit id; C0, C1 and C2 therefore start from the *same*
commit. Treatment material (C1/C2 ``CLAUDE.md``) and runtime seeding are added **after** the
commit and stay uncommitted, so no configuration gets its own history.

Git is only ever executed by the harness on trusted trees (the pristine fixture, or a fresh copy
of it before the agent runs). After the agent has run, ``.git`` is agent-controlled
(``core.fsmonitor``, hooks, ``core.pager``...), so the final ``HEAD`` is read from files with
:func:`read_head`, never by running git.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

BASELINE_BRANCH = "main"
BASELINE_NAME = "Developer"
BASELINE_EMAIL = "dev@example.invalid"
BASELINE_DATE = "2000-01-01T00:00:00+0000"
BASELINE_MESSAGE = "Initial commit"

_GIT_CONFIG = (
    "-c", "commit.gpgsign=false",
    "-c", "core.autocrlf=false",
    "-c", "core.safecrlf=false",
    "-c", f"init.defaultBranch={BASELINE_BRANCH}",
    "-c", "gc.auto=0",
)


class BaselineError(RuntimeError):
    """The pristine baseline could not be created."""


def _git_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "SystemRoot", "HOME")}
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": BASELINE_NAME, "GIT_AUTHOR_EMAIL": BASELINE_EMAIL,
        "GIT_AUTHOR_DATE": BASELINE_DATE,
        "GIT_COMMITTER_NAME": BASELINE_NAME, "GIT_COMMITTER_EMAIL": BASELINE_EMAIL,
        "GIT_COMMITTER_DATE": BASELINE_DATE,
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C", "TZ": "UTC",
    })
    return env


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *_GIT_CONFIG, *args], cwd=str(repo), env=_git_env(),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise BaselineError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace')}")
    return proc.stdout.decode("utf-8", "replace").strip()


def create_baseline(repo: Path) -> str:
    """Turn a fresh copy of the pristine fixture into a one-commit repository; return the id."""
    repo = Path(repo)
    if (repo / ".git").exists():
        raise BaselineError(f"refusing to create a baseline over existing history: {repo}")
    _git(repo, "init", "-q", "--template=")      # no sample hooks, no description/info files
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "--allow-empty", "-m", BASELINE_MESSAGE)
    return _git(repo, "rev-parse", "HEAD")


def expected_baseline_commit(pristine: Path) -> str:
    """The commit id a working copy of ``pristine`` must start from (built on a temp copy)."""
    tmp = Path(tempfile.mkdtemp(prefix="cclab-baseline-"))
    try:
        dest = tmp / "repo"
        shutil.copytree(pristine, dest, symlinks=True)
        return create_baseline(dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def read_head(repo: Path) -> Optional[str]:
    """``HEAD``'s commit id read from files only (no git execution on agent-controlled state).

    Returns None if it cannot be determined (no repo, unborn branch, unusual layout)."""
    git_dir = Path(repo) / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith("ref: "):
        return head or None
    ref = head[5:].strip()
    try:
        return (git_dir / ref).read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    try:
        for line in (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    except OSError:
        pass
    return None


def baseline_record(pristine: Path, expected: str, observed: Optional[str]) -> dict:
    return {
        "pristine_fixture": Path(pristine).name,
        "expected_commit": expected,
        "observed_commit": observed,
        "matches": expected == observed,
        "metadata": {"branch": BASELINE_BRANCH, "author": f"{BASELINE_NAME} <{BASELINE_EMAIL}>",
                     "date": BASELINE_DATE, "message": BASELINE_MESSAGE},
    }


_EXPECTED_CACHE: dict[tuple[str, str], str] = {}


def cached_expected_baseline_commit(pristine: Path) -> str:
    """:func:`expected_baseline_commit`, cached per (fixture path, fixture content hash)."""
    from .hashing import tree_hash

    key = (str(Path(pristine).resolve()), tree_hash(pristine, ignore_dirs=()))
    if key not in _EXPECTED_CACHE:
        _EXPECTED_CACHE[key] = expected_baseline_commit(pristine)
    return _EXPECTED_CACHE[key]
