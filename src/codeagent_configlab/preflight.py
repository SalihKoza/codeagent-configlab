"""Pre-run environment gate (protocol §4/§16).

Preflight is the clean insertion point for the contamination checks the protocol requires
before a run may start. This skeleton implements the ancestor-instruction-file check (which the
clean-run contract §4 mandates) and *registers* the remaining contamination checks as
``DEFERRED`` — explicitly surfaced, never silently treated as passing. That satisfies "do NOT
silently assume end-of-run purge proves a clean start" while leaving the real implementations
for the freeze phase (O3).

A preflight passes only if no check returned ``FAILED``. ``DEFERRED`` results are reported (so
they are visible and cannot be forgotten) but do not by themselves block a smoke run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .status import Preflight
from .workspace import check_ancestor_instructions


@dataclass
class PreflightContext:
    """Inputs a preflight check may consult.

    The optional fields are populated for a real run so the run-start checks can verify that no
    state pre-exists for *this* run's working copy / session / temp slug. They default to
    ``None`` so the existing offline checks and tests keep working unchanged.
    """

    working_copy: Path
    home: Path = field(default_factory=lambda: Path("/home/cclab"))
    pristine: Optional[Path] = None
    harness_root: Optional[Path] = None
    session_uuid: Optional[str] = None
    uid: Optional[int] = None
    # Treatment-aware checks (G9). The expected root instruction files come from the frozen
    # manifest: {} for C0, {"CLAUDE.md": <manifest.claude_md_hash>} for C1/C2. The default ({})
    # is the strict C0 expectation, so a caller that says nothing allows no instruction file.
    expected_treatment_files: dict[str, str] = field(default_factory=dict)
    provenance_errors: list[str] = field(default_factory=list)


@dataclass
class CheckOutcome:
    name: str
    status: Preflight
    detail: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status.value, "detail": self.detail}


@dataclass
class PreflightReport:
    outcomes: list[CheckOutcome]

    @property
    def ok(self) -> bool:
        """True iff no check FAILED. DEFERRED checks are reported but do not block."""
        return all(o.status is not Preflight.FAILED for o in self.outcomes)

    @property
    def deferred(self) -> list[CheckOutcome]:
        return [o for o in self.outcomes if o.status is Preflight.DEFERRED]

    def to_dict(self) -> dict:
        return {"ok": self.ok, "outcomes": [o.to_dict() for o in self.outcomes]}


CheckFn = Callable[[PreflightContext], CheckOutcome]


def check_ancestor_instruction_files(ctx: PreflightContext) -> CheckOutcome:
    """FAIL if any CLAUDE.md/instruction file exists in a directory *above* the WC (§4).

    The working-copy root itself is checked by :func:`check_treatment_instruction_files`, which
    knows the exact treatment file expected for this configuration.
    """
    found = check_ancestor_instructions(ctx.working_copy.resolve().parent)
    if found:
        return CheckOutcome(
            name="ancestor_instruction_files",
            status=Preflight.FAILED,
            detail="found: " + ", ".join(str(p) for p in found),
        )
    return CheckOutcome(name="ancestor_instruction_files", status=Preflight.OK)


def check_treatment_instruction_files(ctx: PreflightContext) -> CheckOutcome:
    """FAIL unless the working copy's instruction state is exactly the expected one (G9 + G7).

    Instruction state = every ``CLAUDE.md`` / ``CLAUDE.local.md`` at any depth plus everything
    under any ``.claude/`` directory (:func:`codeagent_configlab.treatment.is_instruction_path`).
    Allowed: the frozen treatment files with the manifest SHA-256 (C1/C2 ``CLAUDE.md``; nothing
    for C0) and the two Candidate-2 seeded settings files with exactly the seed content. Anything
    else -- a root or nested instruction file, ``.claude/CLAUDE.md``, ``.claude/rules/*`` -- FAILS.
    The pristine fixture itself must contain no instruction material at all.
    """
    from .agent_state import STATE_IGNORED_DIRS
    from .hashing import sha256_bytes
    from .orchestration import snapshot_tree
    from .treatment import instruction_state
    from .workspace import SEED_CONTENT, SEEDED_FILES

    problems: list[str] = []
    expected = ctx.expected_treatment_files
    seed_hash = sha256_bytes(SEED_CONTENT)
    present = instruction_state(snapshot_tree(ctx.working_copy, ignore_dirs=STATE_IGNORED_DIRS))
    for rel in sorted(expected):
        if rel not in present:
            problems.append(f"expected treatment {rel} missing")
        elif present[rel] != expected[rel]:
            problems.append(f"{rel} hash does not match the frozen treatment")
    for rel, digest in present.items():
        if rel in expected:
            continue
        if rel in SEEDED_FILES and digest == seed_hash:
            continue
        problems.append(f"unexpected instruction material {rel} in working copy")
    if ctx.pristine is not None:
        shipped = sorted(instruction_state(snapshot_tree(ctx.pristine, ignore_dirs=STATE_IGNORED_DIRS)))
        if shipped:
            problems.append("pristine fixture ships instruction material: " + ", ".join(shipped))
    if problems:
        return CheckOutcome("treatment_instruction_files", Preflight.FAILED, "; ".join(problems))
    return CheckOutcome("treatment_instruction_files", Preflight.OK,
                        "expected: " + (", ".join(sorted(expected)) or "none"))


def check_treatment_provenance(ctx: PreflightContext) -> CheckOutcome:
    """FAIL if the supplied treatment / statement does not match the frozen manifest hashes."""
    if ctx.provenance_errors:
        return CheckOutcome("treatment_provenance", Preflight.FAILED, "; ".join(ctx.provenance_errors))
    return CheckOutcome("treatment_provenance", Preflight.OK)


def _deferred(name: str, detail: str) -> CheckFn:
    def fn(_ctx: PreflightContext) -> CheckOutcome:
        return CheckOutcome(name=name, status=Preflight.DEFERRED, detail=detail)

    return fn


def _project_slug(working_copy: Path) -> str:
    """Claude's per-project slug: the absolute path with '/' and '.' replaced by '-'.

    Backslash/colon are also neutralized so the slug is a single relative segment (see
    :func:`codeagent_configlab.cleanup.wc_slug`); on the POSIX runtime only '/' and '.' occur.
    """
    import re

    return re.sub(r"[\\/.:]", "-", str(working_copy))


# --- real run-start checks (fail-closed) ------------------------------------------------

def check_user_level_instructions(ctx: PreflightContext) -> CheckOutcome:
    """FAIL if user-level instruction material exists under ~/.claude (§4).

    Only genuine instruction sources are checked (CLAUDE.md, CLAUDE.local.md, skills/). The
    per-WC seeded settings live in the working copy, not here, so they are never flagged.
    """
    claude = ctx.home / ".claude"
    hits = [str(claude / n) for n in ("CLAUDE.md", "CLAUDE.local.md") if (claude / n).exists()]
    if (claude / "skills").is_dir() and any((claude / "skills").iterdir()):
        hits.append(str(claude / "skills") + "/*")
    if hits:
        return CheckOutcome("user_level_instructions", Preflight.FAILED, "found: " + ", ".join(hits))
    return CheckOutcome("user_level_instructions", Preflight.OK)


def check_working_copy_unmodified(ctx: PreflightContext) -> CheckOutcome:
    """FAIL if the freshly created working copy already differs from the pristine fixture.

    Uses :func:`~codeagent_configlab.workspace.changed_files`, which excludes generated caches
    and the intentional per-WC ``.claude`` seeding — so Candidate-2 seeding is not contamination.
    """
    if ctx.pristine is None:
        return CheckOutcome("working_copy_unmodified", Preflight.DEFERRED, "no pristine provided")
    from .workspace import changed_files

    cf = changed_files(ctx.pristine, ctx.working_copy, expected_extra=ctx.expected_treatment_files)
    if cf["added"] or cf["modified"] or cf["deleted"]:
        return CheckOutcome("working_copy_unmodified", Preflight.FAILED, f"pre-existing changes: {cf}")
    return CheckOutcome("working_copy_unmodified", Preflight.OK)


def check_no_project_state(ctx: PreflightContext) -> CheckOutcome:
    """FAIL if Claude project state (incl. auto-memory) already exists for THIS WC path.

    Because the working-copy path is fresh and opaque, its per-project dir
    ``~/.claude/projects/<slug>`` cannot legitimately pre-exist; if it does, a prior run leaked
    into this path and any ``memory/`` under it would be inherited. This does NOT require the
    projects directory to be globally empty, so unrelated old smoke projects do not fail.
    """
    proj = ctx.home / ".claude" / "projects" / _project_slug(ctx.working_copy)
    if proj.exists():
        return CheckOutcome("no_project_state", Preflight.FAILED, f"pre-existing project state: {proj}")
    return CheckOutcome("no_project_state", Preflight.OK)


def check_no_session_env(ctx: PreflightContext) -> CheckOutcome:
    """FAIL if ~/.claude/session-env/<uuid> already exists for this run's session id."""
    if not ctx.session_uuid:
        return CheckOutcome("no_session_env", Preflight.DEFERRED, "no session uuid provided")
    p = ctx.home / ".claude" / "session-env" / ctx.session_uuid
    if p.exists():
        return CheckOutcome("no_session_env", Preflight.FAILED, f"pre-existing session-env: {p}")
    return CheckOutcome("no_session_env", Preflight.OK)


def check_no_tmp_slug(ctx: PreflightContext) -> CheckOutcome:
    """FAIL if /tmp/claude/claude-<uid>/<wc-slug> already exists for this run."""
    if ctx.uid is None:
        return CheckOutcome("no_tmp_slug", Preflight.DEFERRED, "no uid provided")
    p = Path(f"/tmp/claude/claude-{ctx.uid}") / _project_slug(ctx.working_copy)
    if p.exists():
        return CheckOutcome("no_tmp_slug", Preflight.FAILED, f"pre-existing tmp slug: {p}")
    return CheckOutcome("no_tmp_slug", Preflight.OK)


# Registry: the offline default (unchanged) keeps the freeze-phase items DEFERRED and visible.
DEFAULT_CHECKS: list[CheckFn] = [
    check_ancestor_instruction_files,
    check_treatment_instruction_files,
    check_treatment_provenance,
    _deferred("no_foreign_project_state", "verify ~/.claude/projects holds no unexpected project dirs (O3)"),
    _deferred("no_foreign_memory_state", "verify no readable auto-memory from other runs (O3)"),
    _deferred("no_user_level_treatment", "verify ~/.claude/CLAUDE.md, settings.json, skills/ absent (§4)"),
    _deferred("no_leftover_run_state", "verify no leftover session-env/tmp state for this run (§4/§15)"),
]

# The fail-closed checks used for a real run-start (require the richer PreflightContext).
RUN_START_CHECKS: list[CheckFn] = [
    check_ancestor_instruction_files,
    check_treatment_instruction_files,
    check_treatment_provenance,
    check_user_level_instructions,
    check_working_copy_unmodified,
    check_no_project_state,
    check_no_session_env,
    check_no_tmp_slug,
]


def run_start_checks() -> list[CheckFn]:
    """The fail-closed check list for a real run (see :data:`RUN_START_CHECKS`)."""
    return list(RUN_START_CHECKS)


def run_preflight(ctx: PreflightContext, checks: Optional[list[CheckFn]] = None) -> PreflightReport:
    checks = checks if checks is not None else DEFAULT_CHECKS
    return PreflightReport(outcomes=[c(ctx) for c in checks])
