"""Real task evaluator (G5): copy-based, trusted-restore, hidden-inject, command checks.

Order, every time (protocol §6, ``docs/PILOT_TASK_STANDARD.md`` §7):

1. copy the candidate state (the agent's final working copy, or an offline validity state) into
   a throwaway directory -- the candidate directory itself is never modified;
2. restore every task-level protected path in the copy from the trusted pristine fixture (a
   protected path that does not exist in pristine is removed); an agent change to a protected
   path is recorded and reported as ``integrity=protected_path_modified`` (an outcome, F13);
3. inject the hidden test material (kept outside every agent-visible location) into the copy;
4. prepare the evaluator sandbox (G5s, :mod:`codeagent_configlab.evaluator_sandbox`) and prove
   it works with a preflight command inside it;
5. run acceptance, optional structural, and regression commands **inside that sandbox** with a
   fixed minimal environment; nothing is inherited that could carry credentials;
6. re-run the preflight (post-flight) to detect a sandbox that broke mid-evaluation.

Status semantics: exit 0 = pass, any other exit = fail (a failure caused by agent-written code --
syntax/import error, failing or hanging test -- is a task outcome). ``error`` is reserved for the
evaluator itself: a command that cannot start, an exit code listed in ``error_codes`` (e.g. a
test runner's "usage error"/"no tests collected"), termination failure, missing hidden material,
a restore failure, or any evaluator-sandbox failure (initialization, preflight, post-flight).
Structural checks feed the acceptance axis and are reported separately.

Fail closed (G5s): without a sandbox (``sandbox=None``) nothing is executed and the result is an
evaluator error. A sandbox failure is never retried and never followed by an unsandboxed run. The
production sandbox is :func:`~codeagent_configlab.evaluator_sandbox.production_evaluator_sandbox`
(srt, Linux/WSL only); tests may inject a fake whose ``record()`` says ``production_safe: false``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from .evaluator import EvaluationResult
from .status import Acceptance, Integrity, Regression

OUTPUT_TAIL_BYTES = 4096
PASS, FAIL, ERROR = "pass", "fail", "error"


@dataclass(frozen=True)
class CheckSpec:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: float = 120.0
    error_codes: tuple[int, ...] = ()


@dataclass(frozen=True)
class TaskEvaluatorSpec:
    """Everything the evaluator needs for one task. All paths live outside the agent's reach."""

    pristine: Path                          # trusted source for protected paths
    acceptance: tuple[CheckSpec, ...]
    regression: tuple[CheckSpec, ...]
    structural: tuple[CheckSpec, ...] = ()
    protected_paths: tuple[str, ...] = ()   # relative posix paths (files or directories)
    hidden_dir: Optional[Path] = None       # hidden tests; copied into the evaluation copy only
    hidden_dest: str = "_hidden_tests"      # where in the copy they are placed
    env: tuple[tuple[str, str], ...] = ()   # fixed extra environment
    # package-declared build/runtime outputs; removed from the evaluator copy before any check so
    # outputs hidden from the diff can never influence a verdict (rebuilt from source by checks)
    generated_outputs: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.acceptance or not self.regression:
            raise ValueError("a task needs at least one acceptance and one regression check")
        from .agent_state import validate_generated_patterns

        errors = validate_generated_patterns(self.generated_outputs)
        if errors:
            raise ValueError(f"invalid generated_outputs: {errors}")
        for rel in (*self.protected_paths, self.hidden_dest):
            p = PurePosixPath(rel)
            if p.is_absolute() or ".." in p.parts or not p.parts:
                raise ValueError(f"evaluator paths must be relative and inside the copy: {rel!r}")


def _tail(data: bytes) -> str:
    return data[-OUTPUT_TAIL_BYTES:].decode("utf-8", "replace")


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _same(a: Path, b: Path) -> bool:
    """True if two paths hold identical content (files or trees); symlinks compare by target."""
    from .orchestration import snapshot_tree

    if a.is_symlink() or b.is_symlink():
        return a.is_symlink() and b.is_symlink() and os.readlink(a) == os.readlink(b)
    if a.is_file() and b.is_file():
        return a.read_bytes() == b.read_bytes()
    if a.is_dir() and b.is_dir():
        return snapshot_tree(a, ignore_dirs=()) == snapshot_tree(b, ignore_dirs=())
    return not a.exists() and not b.exists()


def _base_env(home: Path, extra) -> dict:
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "SystemRoot", "COMSPEC") if k in os.environ}
    env.update({"HOME": str(home), "TMPDIR": str(home), "TMP": str(home), "TEMP": str(home),
                "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1", "CI": "1"})
    env.update(dict(extra))
    return env


def _run_command(argv: list[str], cwd: Path, env: dict, timeout: float) -> dict:
    """Run one (already sandbox-wrapped) check command; never raises for command-level problems.

    On Linux every command goes through the G1 process-tree runner. The plain ``subprocess.run``
    branch exists only where ``/proc`` is absent (Windows development); the srt sandbox refuses to
    prepare there, so that branch can never carry a benchmark evaluation.
    """
    try:
        if os.path.isdir("/proc/self"):
            from .process_control import TERMINATION_FAILED, Deadline, run_with_deadline

            res = run_with_deadline(argv, cwd=str(cwd), env=env, deadline=Deadline.start(timeout),
                                    terminate_grace=2.0, kill_wait=2.0, drain_timeout=2.0)
            return {"exit_code": res.returncode, "timed_out": res.timed_out,
                    "termination_failed": res.termination == TERMINATION_FAILED,
                    "stdout": res.stdout, "stderr": res.stderr, "spawn_error": None}
        # Development fallback (no /proc, e.g. Windows): no process-tree guarantee.
        proc = subprocess.run(argv, cwd=str(cwd), env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout)
        return {"exit_code": proc.returncode, "timed_out": False, "termination_failed": False,
                "stdout": proc.stdout, "stderr": proc.stderr, "spawn_error": None}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": None, "timed_out": True, "termination_failed": False,
                "stdout": exc.stdout or b"", "stderr": exc.stderr or b"", "spawn_error": None}
    except OSError as exc:
        return {"exit_code": None, "timed_out": False, "termination_failed": False,
                "stdout": b"", "stderr": b"", "spawn_error": f"{type(exc).__name__}: {exc}"}


# G8: the in-sandbox launcher prints this trailer as the LAST stdout line after the check command
# returns: ``CCLAB-EVAL-RC:<per-check nonce>:<exit status>``. Only a trailer that matches the
# process exit code attests that the command really ran inside the sandbox; anything else is an
# evaluator infrastructure error, never a task verdict.
EXIT_TRAILER_PREFIX = "CCLAB-EVAL-RC:"
SH_CHECK_LAUNCHER = ('n=$1; shift; "$@"; rc=$?; '
                     'printf "\\n' + EXIT_TRAILER_PREFIX + '%s:%s\\n" "$n" "$rc"; exit "$rc"')


def split_exit_trailer(stdout: bytes, nonce: str) -> tuple[Optional[int], bytes]:
    """(attested exit status or None, stdout without the launcher trailer)."""
    data = stdout or b""
    marker = f"{EXIT_TRAILER_PREFIX}{nonce}:".encode()
    body, sep, last = data.rstrip(b"\n").rpartition(b"\n")
    if not sep:
        body, last = b"", data.rstrip(b"\n")
    if not last.startswith(marker):
        return None, data
    try:
        return int(last[len(marker):].decode("ascii")), body
    except ValueError:
        return None, data


def _axis(statuses: list[str]):
    if any(s == ERROR for s in statuses):
        return ERROR
    if any(s == FAIL for s in statuses):
        return FAIL
    return PASS


@dataclass
class TaskEvaluator:
    spec: TaskEvaluatorSpec
    # The command_wrapper seam (G5s): an object with prepare/wrap/env/resolve_program/
    # preflight_argv/record -- normally evaluator_sandbox.SrtEvaluatorSandbox. None = fail closed.
    sandbox: Optional[Any] = None
    preflight_timeout: float = 60.0

    def evaluate(self, final_working_copy: Path) -> EvaluationResult:
        spec = self.spec
        root = Path(tempfile.mkdtemp(prefix="cclab-taskeval-"))
        candidate = Path(final_working_copy)
        try:
            work, home = root / "wc", root / "home"
            restoration, integrity, injected = [], Integrity.CLEAN, []
            try:
                home.mkdir()
                if not Path(spec.pristine).is_dir():
                    # without the trusted source every protected path would silently be "removed"
                    raise FileNotFoundError("trusted pristine fixture missing")
                # .git is agent-controlled after the run and is never needed by checks.
                shutil.copytree(candidate, work, symlinks=True, ignore=shutil.ignore_patterns(".git"))
                for rel in spec.protected_paths:
                    trusted, target = spec.pristine / rel, work / rel
                    modified = not _same(trusted, candidate / rel)
                    if target.exists() or target.is_symlink():
                        _remove(target)
                    if trusted.is_dir():
                        shutil.copytree(trusted, target, symlinks=True)
                        action = "restored"
                    elif trusted.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(trusted, target)
                        action = "restored"
                    else:
                        action = "removed"   # must not exist for evaluation
                    restoration.append({"path": rel, "agent_modified": modified, "action": action})
                    if modified:
                        integrity = Integrity.PROTECTED_PATH_MODIFIED

                if spec.generated_outputs:
                    from .agent_state import is_generated
                    from .orchestration import snapshot_tree

                    for rel in sorted(snapshot_tree(work, ignore_dirs=(".git",))):
                        if is_generated(rel, spec.generated_outputs):
                            _remove(work / rel)
                            restoration.append({"path": rel, "agent_modified": False,
                                                "action": "generated_removed"})
                if spec.hidden_dir is not None:
                    if not Path(spec.hidden_dir).is_dir():
                        raise FileNotFoundError("hidden test material missing")
                    dest = work / spec.hidden_dest
                    if dest.exists() or dest.is_symlink():
                        restoration.append({"path": spec.hidden_dest, "agent_modified": True,
                                            "action": "replaced_by_hidden"})
                        integrity = Integrity.PROTECTED_PATH_MODIFIED
                        _remove(dest)
                    shutil.copytree(spec.hidden_dir, dest)
                    injected = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
            except Exception as exc:
                return EvaluationResult(Acceptance.ERROR, Regression.ERROR, integrity=integrity,
                                        evaluator_error=True, restoration=restoration,
                                        detail=f"evaluator setup failed: {type(exc).__name__}: {exc}")

            all_specs = [(kind, c) for kind, specs in (("acceptance", spec.acceptance),
                                                        ("structural", spec.structural),
                                                        ("regression", spec.regression))
                         for c in specs]
            sandbox = self.sandbox
            if sandbox is None:
                return _sandbox_failure(all_specs, integrity, restoration, injected, {},
                                        "no evaluator sandbox configured (fail closed); "
                                        "no check was executed")
            record = sandbox.record()
            try:
                sandbox.prepare(root, work, home)
                env = _base_env(home, spec.env)
                env.update(sandbox.env())
                programs = sorted({sandbox.resolve_program(c.argv[0], work) for _, c in all_specs})
            except Exception as exc:
                return _sandbox_failure(all_specs, integrity, restoration, injected, record,
                                        "evaluator sandbox initialization failed: "
                                        f"{type(exc).__name__}: {exc}")
            pre = self._flight(sandbox, programs, work, env)
            if pre is not None:
                return _sandbox_failure(all_specs, integrity, restoration, injected, record,
                                        f"evaluator sandbox preflight failed: {pre}")

            checks = []
            for kind, c in all_specs:
                nonce = uuid.uuid4().hex
                try:
                    argv = sandbox.wrap_check(list(c.argv), work, nonce)
                except Exception as exc:
                    r = {"exit_code": None, "timed_out": False, "termination_failed": False,
                         "stdout": b"", "stderr": b"",
                         "spawn_error": f"sandbox wrap failed: {type(exc).__name__}: {exc}"}
                else:
                    r = _run_command(argv, work, env, c.timeout_seconds)
                attested, r["stdout"] = split_exit_trailer(r["stdout"], nonce)
                if r["spawn_error"] or r["termination_failed"]:
                    status, reason = ERROR, r["spawn_error"] or "check process tree not terminated"
                elif r["timed_out"]:
                    status, reason = FAIL, f"check exceeded {c.timeout_seconds}s"
                elif attested is None or attested != r["exit_code"]:
                    # G8: the sandbox did not attest that the command ran and returned this status
                    # (srt/launcher failed, or the boundary was disturbed). Never a task verdict.
                    status, reason = ERROR, (
                        f"evaluator sandbox did not attest the check's exit status "
                        f"(process exit {r['exit_code']}, attested {attested})")
                elif r["exit_code"] in c.error_codes:
                    status, reason = ERROR, f"exit code {r['exit_code']} marks an evaluator error"
                elif r["exit_code"] == 0:
                    status, reason = PASS, ""
                else:
                    status, reason = FAIL, f"exit code {r['exit_code']}"
                checks.append({"kind": kind, "name": c.name, "status": status, "reason": reason,
                               "exit_code": r["exit_code"], "timed_out": r["timed_out"],
                               "stdout_tail": _tail(r["stdout"]), "stderr_tail": _tail(r["stderr"])})

            post = self._flight(sandbox, programs, work, env)
            if post is not None:   # the sandbox broke mid-evaluation: no verdict is trustworthy
                return EvaluationResult(Acceptance.ERROR, Regression.ERROR, integrity=integrity,
                                        evaluator_error=True, checks=checks,
                                        restoration=restoration, injected=injected, sandbox=record,
                                        detail=f"evaluator sandbox post-flight failed: {post}")
            acc = _axis([c["status"] for c in checks if c["kind"] in ("acceptance", "structural")])
            reg = _axis([c["status"] for c in checks if c["kind"] == "regression"])
            return EvaluationResult(
                acceptance=Acceptance(acc), regression=Regression(reg), integrity=integrity,
                evaluator_error=ERROR in (acc, reg), checks=checks, restoration=restoration,
                injected=injected, sandbox=record,
                detail="task evaluation on a copy of the candidate state",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _flight(self, sandbox, programs: list[str], work: Path, env: dict) -> Optional[str]:
        """Run the sandbox's sentinel command inside the sandbox. None = OK, else a diagnostic."""
        nonce = f"cclab-evalsbx-ok-{uuid.uuid4().hex}"
        try:
            argv = sandbox.wrap(sandbox.preflight_argv(programs, nonce), work)
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
        r = _run_command(argv, work, env, self.preflight_timeout)
        if (r["spawn_error"] or r["termination_failed"] or r["timed_out"] or r["exit_code"] != 0
                or nonce.encode() not in r["stdout"]):
            return (f"exit={r['exit_code']} timed_out={r['timed_out']} "
                    f"spawn_error={r['spawn_error']} stdout={_tail(r['stdout'])[-300:]!r} "
                    f"stderr={_tail(r['stderr'])[-600:]!r}")
        return None


def _sandbox_failure(all_specs, integrity, restoration, injected, record, reason) -> EvaluationResult:
    """Every check is an evaluator error; none was executed (and none is run unsandboxed)."""
    checks = [{"kind": kind, "name": c.name, "status": ERROR, "reason": reason, "exit_code": None,
               "timed_out": False, "stdout_tail": "", "stderr_tail": ""} for kind, c in all_specs]
    return EvaluationResult(Acceptance.ERROR, Regression.ERROR, integrity=integrity,
                            evaluator_error=True, checks=checks, restoration=restoration,
                            injected=injected, sandbox=record, detail=reason)


# --- offline task-validity entry points (PILOT_TASK_STANDARD §11) ---------------------------

def evaluate_candidate(spec: TaskEvaluatorSpec, state_dir: Path, sandbox=None) -> EvaluationResult:
    """Evaluate any candidate state -- pristine, reference, known-wrong or an agent's final copy.

    Without a ``sandbox`` the result is an evaluator error (fail closed, G5s).
    """
    return TaskEvaluator(spec, sandbox=sandbox).evaluate(Path(state_dir))


def overlay_candidate(pristine: Path, overlay_dir: Optional[Path], dest: Path,
                      deletions: tuple[str, ...] = ()) -> Path:
    """Build a candidate state = pristine + overlay files - deletions (for validity gates)."""
    dest = Path(dest)
    shutil.copytree(pristine, dest, symlinks=True)
    if overlay_dir is not None:
        shutil.copytree(overlay_dir, dest, symlinks=True, dirs_exist_ok=True)
    for rel in deletions:
        _remove(dest / rel)
    return dest
