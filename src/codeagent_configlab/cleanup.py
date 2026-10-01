"""Per-run Claude-state cleanup (protocol §15), using only the verified narrow mechanism.

The readiness spike (Spike D) established a narrow, exact-name cleanup that removes a run's
project-local Claude state without touching auth or other projects:

1. ``claude project purge -y <working-copy>``
2. ``rm -rf ~/.claude/session-env/<uuid>``   (exact UUID name)
3. ``rm -rf /tmp/claude/claude-<uid>/<wc-slug>``  (exact slug)

This module builds that plan as an inspectable list of argv commands and **guards their
scope**: it refuses to emit any command that would delete ``~/.claude`` broadly, the home
directory, or a glob. Nothing here executes by default; :func:`build_cleanup_plan` returns the
commands and a runner may execute them after artifacts are captured (never before).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_UUID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")


class CleanupScopeError(ValueError):
    """Raised when a proposed cleanup command is too broad to be safe."""


@dataclass(frozen=True)
class CleanupCommand:
    argv: tuple[str, ...]
    purpose: str


def wc_slug(working_copy: str) -> str:
    """Project slug Claude uses under /tmp: path with '/' and '.' replaced by '-'.

    Backslash and colon are also neutralized so a slug is always a single relative segment;
    on the POSIX runtime those characters never occur in a working-copy path, so this matches
    Claude's actual behavior there while staying robust if a caller passes a native path.
    """
    return re.sub(r"[\\/.:]", "-", working_copy)


def _assert_safe_rm(path: str) -> None:
    """Refuse dangerous rm -rf targets: only exact-name paths under the two allowed parents.

    Allowed parents are ``~/.claude/session-env/`` and ``/tmp/claude/``. Anything else — a broad
    ``~/.claude``, the home dir, ``/``, or a glob/space-bearing target — is refused.
    """
    p = path.rstrip("/")
    if p in ("", "/", "~", "/home/cclab", "/home/cclab/.claude"):
        raise CleanupScopeError(f"refusing broad rm target: {path!r}")
    if any(ch in path for ch in "*?[") or " " in path:
        raise CleanupScopeError(f"refusing rm target with glob/space: {path!r}")
    if not (
        p.startswith("/home/cclab/.claude/session-env/")
        or p.startswith("/tmp/claude/")
    ):
        raise CleanupScopeError(f"rm target not under an allowed exact-name parent: {path!r}")


def build_cleanup_plan(
    working_copy: str,
    session_uuids: list[str],
    *,
    uid: int = 1001,
    home: str = "/home/cclab",
) -> list[CleanupCommand]:
    """Build the exact, scoped cleanup command list for one run.

    ``session_uuids`` is every session id the run created (one for C0/C1, one for C2 — phase 2
    resumes the same id). Raises :class:`CleanupScopeError` if any target is unsafe.
    """
    if not working_copy or working_copy in ("/", home, f"{home}/.claude"):
        raise CleanupScopeError(f"refusing to purge broad working-copy path: {working_copy!r}")

    plan: list[CleanupCommand] = [
        CleanupCommand(
            argv=("claude", "project", "purge", "-y", working_copy),
            purpose="remove project transcripts/memory/config entry for this working copy",
        )
    ]
    for u in session_uuids:
        if not _UUID_RE.match(u):
            raise CleanupScopeError(f"refusing non-UUID session id: {u!r}")
        target = f"{home}/.claude/session-env/{u}"
        _assert_safe_rm(target)
        plan.append(
            CleanupCommand(
                argv=("rm", "-rf", "--", target),
                purpose=f"remove exact session-env dir for {u}",
            )
        )
    tmp_target = f"/tmp/claude/claude-{uid}/{wc_slug(working_copy)}"
    _assert_safe_rm(tmp_target)
    plan.append(
        CleanupCommand(
            argv=("rm", "-rf", "--", tmp_target),
            purpose="remove exact per-project /tmp/claude dir",
        )
    )
    return plan


def plan_to_dict(plan: list[CleanupCommand]) -> dict:
    """Serialize a plan for the cleanup artifact/report."""
    return {"commands": [{"argv": list(c.argv), "purpose": c.purpose} for c in plan]}


def verify_residue(plan: list[CleanupCommand], *, home: str) -> dict:
    """Post-hoc, read-only check: did each cleanup command's target actually disappear?

    Never executes anything itself. For the ``claude project purge`` command the target is the
    per-project state dir Claude would have removed (``<home>/.claude/projects/<slug>``, the same
    slug transform as the exact-name ``rm -rf`` targets); for each ``rm -rf -- <target>`` command
    the target is simply its own last argv element.
    """
    targets = []
    for c in plan:
        if c.argv[:3] == ("claude", "project", "purge"):
            working_copy = c.argv[-1]
            target = f"{home}/.claude/projects/{wc_slug(working_copy)}"
        elif c.argv[:2] == ("rm", "-rf"):
            target = c.argv[-1]
        else:
            continue
        targets.append({"purpose": c.purpose, "target": target,
                        "clear": not Path(target).exists()})
    return {"targets": targets, "all_clear": all(t["clear"] for t in targets)}
