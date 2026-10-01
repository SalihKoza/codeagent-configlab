"""Production execution edges: a real AgentRunner and CleanupRunner for WSL.

These are the only pieces that shell out to ``claude``/``srt``. Everything else in the harness
is offline. They plug into the existing :class:`~codeagent_configlab.lifecycle.RunLifecycle`
via its ``AgentRunner`` / ``CleanupRunner`` protocols, and they build every flag from
:class:`~codeagent_configlab.envelope.ExecutionEnvelope` rather than duplicating flag strings.

Safety properties enforced here:

* the task statement is delivered on **stdin**, never concatenated into a shell command;
* the process runs as an ``argv`` list (no shell), so nothing is word-split or expanded;
* the environment is sanitized (auth-override vars removed) and is **never** written to an
  artifact; the full environment is never dumped;
* credentials are never read or captured;
* cleanup uses only the exact, scope-guarded plan from
  :func:`~codeagent_configlab.cleanup.build_cleanup_plan`.

``spawn`` is injectable (defaults to :func:`subprocess.run`) so the argv/stdin/env construction
can be tested offline without invoking a real model.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from glob import glob
from pathlib import Path
from typing import Callable, Optional

from .cleanup import CleanupCommand
from .envelope import AUTH_OVERRIDE_VARS, ExecutionEnvelope
from .lifecycle import AgentRunOutcome
from .outcome_classifier import classify_invocation
from .process_control import (
    NOT_STARTED,
    TERMINATION_FAILED,
    Deadline,
    ProcessRunResult,
    run_with_deadline,
)
from .session import SessionSpec, observed_model_in_events, session_ids_in_events
from .status import AgentOutcome
from .workspace import WorkingCopy

SpawnFn = Callable[..., subprocess.CompletedProcess]      # cleanup commands
AgentSpawnFn = Callable[..., ProcessRunResult]             # the agent invocation (G1)

# Marks "no per-call deadline given": fall back to the runner's own deadline/timeout.
_UNSET = object()

def _resolve_exe(name: str, home: str) -> str:
    """Absolute path to ``name`` (claude/srt), preferring PATH then known WSL locations."""
    found = shutil.which(name)
    # WSL appends the Windows PATH; a /mnt/<drive> binary is a Windows install (outside the
    # sandbox view, wrong account state) and must never be used by the harness.
    if found and not found.startswith("/mnt/"):
        return found
    candidates = [f"{home}/.local/bin/{name}"]
    candidates += sorted(glob(f"{home}/.nvm/versions/node/*/bin/{name}"), reverse=True)
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError(f"could not resolve executable {name!r} (PATH or WSL fallbacks)")


def _sanitized_env(run_tmp: str) -> dict:
    """A copy of the environment with auth-override vars removed and harness vars set.

    Never persisted anywhere. The returned dict is passed straight to the child process.
    """
    env = {k: v for k, v in os.environ.items() if k not in AUTH_OVERRIDE_VARS}
    env["DISABLE_AUTOUPDATER"] = "1"
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["TMPDIR"] = run_tmp
    return env


def _parse_events(stdout: str) -> list[dict]:
    events: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def classify_process_result(
    proc: ProcessRunResult, events: list[dict], stdout: str = "", stderr: str = ""
) -> tuple[AgentOutcome, str, dict]:
    """Map a :class:`ProcessRunResult` + parsed events to an outcome, a reason and the record.

    Thin adapter over :func:`~codeagent_configlab.outcome_classifier.classify_invocation` (G4):
    only structured top-level event fields are evidence; ``stdout`` text and ``stderr`` are
    accepted for interface compatibility but deliberately **not** read. G1 semantics are kept:
    termination failure -> ``harness_error``; an enforced cap -> ``timeout`` unless the cap was
    spent blocked on an auth/limit API error.
    """
    cls = classify_invocation(
        proc.returncode, events, timed_out=proc.timed_out,
        termination_failed=proc.termination == TERMINATION_FAILED,
        not_started=proc.termination == NOT_STARTED,
    )
    if cls.outcome is AgentOutcome.HARNESS_ERROR:
        detail = (f"{cls.reason}: process-tree termination failed: {proc.error or 'survivors'}; "
                  f"survivors={proc.survivors}")
    elif cls.outcome is AgentOutcome.TIMEOUT and proc.termination == NOT_STARTED:
        detail = f"{cls.reason}: wall-clock budget already exhausted; not started"
    elif cls.outcome is AgentOutcome.TIMEOUT:
        detail = (f"{cls.reason}: wall-clock cap of {proc.deadline_budget_seconds}s reached; "
                  f"run-owned process tree terminated "
                  f"({', '.join(proc.signals_sent) or 'no signal needed'})")
    else:
        detail = cls.reason
    return cls.outcome, detail, cls.to_dict()


@dataclass
class RealAgentRunner:
    """Invokes ``claude`` headlessly inside the Candidate-2 outer/inner sandbox.

    Constructed per run with the run-specific model, effort level and task statement (the run
    specification), plus the harness layout. ``spawn`` is injectable for offline tests; it has the signature of
    :func:`~codeagent_configlab.process_control.run_with_deadline`.

    Time cap: ``deadline`` (a shared :class:`Deadline`, e.g. one budget for a future C2 phase 1 +
    phase 2) takes precedence; otherwise ``timeout`` seconds start counting when :meth:`run` is
    called; neither means no cap.
    """

    home: str
    harness_root: str
    model: str
    effort: str
    prompt: str
    tmp_root: Optional[str] = None
    spawn: AgentSpawnFn = run_with_deadline
    timeout: Optional[float] = None
    deadline: Optional[Deadline] = None
    srt_path: Optional[str] = None      # resolved from PATH/WSL fallbacks if None
    claude_path: Optional[str] = None
    # populated after run() so a caller/cleanup can find the exact run tmp dir
    last_run_tmp: Optional[str] = field(default=None, init=False)
    run_tmps: list[str] = field(default_factory=list, init=False)  # one per invocation

    def run(self, working_copy: WorkingCopy, envelope: ExecutionEnvelope, session: SessionSpec,
            *, prompt: Optional[str] = None, deadline=_UNSET) -> AgentRunOutcome:
        """One Claude CLI invocation.

        ``prompt`` overrides the runner's own prompt for this call (C2 sends the planning wrapper,
        then the approval message). An explicit ``deadline`` -- including ``None`` for "no cap" --
        overrides the runner's own ``deadline``/``timeout``; the orchestrator uses this so both
        C2 phases draw from one shared budget and never get a full per-phase cap.
        """
        wc = str(working_copy.path)
        # /tmp/claude must exist (srt forces it as the in-sandbox TMPDIR). Best-effort so the
        # argv/env construction stays testable off-WSL.
        try:
            Path("/tmp/claude").mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError:
            pass
        tmp_base = Path(self.tmp_root or (Path(self.harness_root) / "tmp"))
        tmp_base.mkdir(parents=True, exist_ok=True)
        run_tmp = tempfile.mkdtemp(prefix="", dir=str(tmp_base))
        self.last_run_tmp = run_tmp
        self.run_tmps.append(run_tmp)

        policy = envelope.security_policy
        protect = json.dumps(policy.render_inner_settings(self.home, wc, run_tmp),
                             separators=(",", ":"), sort_keys=True)
        outer = policy.render_outer_srt(envelope.srt_mode, self.home, self.harness_root, wc, run_tmp)
        cfg_path = Path(run_tmp) / "outer-srt.json"
        cfg_path.write_text(json.dumps(outer), encoding="utf-8")

        claude_flags = envelope.build_claude_flags(
            model=self.model, effort=self.effort, session_flag=session.cli_flag(),
            protect_json=protect, add_dir=wc
        )
        srt_abs = self.srt_path or _resolve_exe("srt", self.home)
        claude_abs = self.claude_path or _resolve_exe("claude", self.home)
        argv = [srt_abs, "-s", str(cfg_path), "--", claude_abs, *claude_flags]

        env = _sanitized_env(run_tmp)
        env.update(envelope.loader_env())   # G11 loader: same for every configuration and phase
        if deadline is _UNSET:
            deadline = self.deadline
            if deadline is None and self.timeout is not None:
                deadline = Deadline.start(self.timeout)
        proc = self.spawn(
            argv,
            input=(prompt if prompt is not None else self.prompt).encode("utf-8"),
            cwd=wc,
            env=env,
            deadline=deadline,
        )
        stdout = proc.stdout.decode("utf-8", "replace") if isinstance(proc.stdout, (bytes, bytearray)) else (proc.stdout or "")
        stderr = proc.stderr.decode("utf-8", "replace") if isinstance(proc.stderr, (bytes, bytearray)) else (proc.stderr or "")
        events = _parse_events(stdout)
        outcome, detail, classification = classify_process_result(proc, events)

        sids = session_ids_in_events(events)
        observed = session.session_id if session.session_id in sids else (next(iter(sids)) if sids else None)
        continuity = sids == {session.session_id}
        observed_model = observed_model_in_events(events)

        return AgentRunOutcome(
            exit_code=proc.returncode,
            session_id=observed,
            agent_outcome=outcome,
            stdout=stdout,
            stderr=stderr,
            events=events,
            session_continuity_verified=continuity,
            detail=detail,
            process={**proc.metadata(), "classification": classification,
                    "requested_model": self.model, "observed_model": observed_model},
            observed_model=observed_model,
        )


@dataclass
class RealCleanupRunner:
    """Executes the exact, scope-guarded cleanup plan and records per-command results."""

    home: str = "/home/cclab"
    spawn: SpawnFn = subprocess.run
    extra_paths: tuple[str, ...] = ()  # additional exact paths to rm (e.g. the run tmp dir)

    def execute(self, plan: list[CleanupCommand]) -> dict:
        commands = []
        all_ok = True
        env = {k: v for k, v in os.environ.items() if k not in AUTH_OVERRIDE_VARS}
        env["DISABLE_AUTOUPDATER"] = "1"
        for cmd in plan:
            argv = list(cmd.argv)
            if argv and argv[0] == "claude":
                try:  # the WSL-local CLI, never a Windows install found through the appended PATH
                    argv[0] = _resolve_exe("claude", self.home)
                except FileNotFoundError:
                    pass
            try:
                proc = self.spawn(argv, env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
                ok = proc.returncode == 0
            except Exception as exc:  # a spawn failure is itself a cleanup failure
                commands.append({"argv": list(cmd.argv), "exit": None, "ok": False, "error": str(exc)})
                all_ok = False
                continue
            commands.append({"argv": list(cmd.argv), "exit": proc.returncode, "ok": ok,
                             "purpose": cmd.purpose})
            all_ok = all_ok and ok
        for p in self.extra_paths:
            # only remove exact run-specific tmp dirs, never anything broad
            if p and (p.startswith("/tmp/") or "/tmp/" in p) and " " not in p and "*" not in p:
                try:
                    shutil.rmtree(p, ignore_errors=True)
                    commands.append({"argv": ["rmtree", p], "exit": 0, "ok": True,
                                     "purpose": "remove exact run tmp dir"})
                except Exception as exc:
                    commands.append({"argv": ["rmtree", p], "exit": None, "ok": False, "error": str(exc)})
                    all_ok = False
        return {"commands": commands, "executed": all_ok, "cleanup_failed": not all_ok}
