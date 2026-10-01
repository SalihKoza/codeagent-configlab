"""Run-owned process execution with a wall-clock deadline and process-tree termination (G1).

The agent command runs in its **own session / process group** (``start_new_session=True``), so the
harness can signal everything the run started without touching unrelated processes. The real
topology is ``srt`` (node) -> ``sh -c`` -> ``bwrap --new-session --die-with-parent`` -> ``claude``
(sandbox-runtime 0.0.77): ``bwrap --new-session`` moves the inner tree into *another* session, so a
process-group signal alone is not enough. Descendants are therefore also tracked by their
``/proc`` parent chain, keyed by ``(pid, starttime)`` so a reused PID is never signalled. Nothing
is ever selected by process name.

Outcome semantics (see ``docs/RUN_MANIFEST_V0.md``):

* ``exited`` — the process ended on its own before the deadline.
* ``timeout_terminated`` — the deadline passed and the harness terminated the whole tree. This is
  a correctly enforced cap: an experimental outcome, **not** a harness failure.
* ``not_started_deadline_expired`` — the (shared) deadline had already passed; nothing spawned.
* ``termination_failed`` — the harness could not confirm that the tree is gone (signal error,
  survivor, pipes held open, no ``/proc``). This **is** a harness failure.

:class:`Deadline` is an absolute budget that several sequential invocations can share (the future
C2 phase 1 + phase 2 total cap); this module does not orchestrate C2 itself.
"""

from __future__ import annotations

import os
import signal as _signal_mod
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

EXITED = "exited"
TIMEOUT_TERMINATED = "timeout_terminated"
NOT_STARTED = "not_started_deadline_expired"
TERMINATION_FAILED = "termination_failed"

_DEAD_STATES = ("Z", "X", "x")  # zombie / dead: no longer running


@dataclass(frozen=True)
class Deadline:
    """An absolute wall-clock budget on a monotonic clock, shareable across invocations."""

    budget_seconds: float
    started_at: float
    clock: Callable[[], float] = field(default=time.monotonic, compare=False, repr=False)

    @classmethod
    def start(cls, budget_seconds: float, clock: Callable[[], float] = time.monotonic) -> "Deadline":
        if isinstance(budget_seconds, bool) or not isinstance(budget_seconds, (int, float)):
            raise TypeError(f"budget must be a number of seconds, got {budget_seconds!r}")
        if budget_seconds <= 0:
            raise ValueError(f"budget must be positive, got {budget_seconds!r}")
        return cls(float(budget_seconds), clock(), clock)

    @property
    def expires_at(self) -> float:
        return self.started_at + self.budget_seconds

    def elapsed(self) -> float:
        return self.clock() - self.started_at

    def remaining(self) -> float:
        return max(0.0, self.expires_at - self.clock())

    def expired(self) -> bool:
        return self.remaining() <= 0.0


@dataclass(frozen=True)
class ProcInfo:
    ppid: int
    pgrp: int
    state: str
    starttime: int


def read_proc_table() -> dict[int, ProcInfo]:
    """Snapshot ``/proc/<pid>/stat`` for all visible processes. Raises if ``/proc`` is absent."""
    table: dict[int, ProcInfo] = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", "rb") as fh:
                raw = fh.read().decode("utf-8", "replace")
        except OSError:
            continue  # exited between listdir and open
        # comm (field 2) is parenthesised and may contain spaces: split after the last ')'.
        rest = raw[raw.rfind(")") + 2:].split()
        try:
            table[int(name)] = ProcInfo(ppid=int(rest[1]), pgrp=int(rest[2]), state=rest[0],
                                        starttime=int(rest[19]))
        except (IndexError, ValueError):
            continue
    return table


def descendants(root_pid: int, table: dict[int, ProcInfo]) -> set[int]:
    """PIDs whose parent chain reaches ``root_pid`` (excluding the root)."""
    children: dict[int, list[int]] = {}
    for pid, info in table.items():
        children.setdefault(info.ppid, []).append(pid)
    found: set[int] = set()
    stack = [root_pid]
    while stack:
        for child in children.get(stack.pop(), ()):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


@dataclass
class ProcessRunResult:
    """What happened to one invocation. ``stdout``/``stderr`` hold whatever was emitted."""

    termination: str
    timed_out: bool
    returncode: Optional[int]          # None if harness-terminated or never started
    raw_returncode: Optional[int] = None  # Popen's code as observed (negative = signal)
    signal: Optional[int] = None
    stdout: bytes = b""
    stderr: bytes = b""
    elapsed_seconds: Optional[float] = None
    pid: Optional[int] = None
    pgid: Optional[int] = None
    signals_sent: list[str] = field(default_factory=list)
    tracked_pids: list[int] = field(default_factory=list)
    survivors: list[int] = field(default_factory=list)
    post_exit_swept: list[int] = field(default_factory=list)
    deadline_budget_seconds: Optional[float] = None
    error: Optional[str] = None

    def metadata(self) -> dict:
        """JSON-safe termination metadata (never stdout/stderr, never environment)."""
        return {
            "termination": self.termination,
            "timed_out": self.timed_out,
            "returncode": self.returncode,
            "raw_returncode": self.raw_returncode,
            "signal": self.signal,
            "elapsed_seconds": self.elapsed_seconds,
            "pid": self.pid,
            "pgid": self.pgid,
            "signals_sent": list(self.signals_sent),
            "tracked_pids": list(self.tracked_pids),
            "survivors": list(self.survivors),
            "post_exit_swept": list(self.post_exit_swept),
            "deadline_budget_seconds": self.deadline_budget_seconds,
            "error": self.error,
        }


class _TreeTerminator:
    """Terminates everything owned by one run: its process group plus tracked descendants."""

    def __init__(self, proc: subprocess.Popen, send: Callable[[int, int], None],
                 proc_table: Callable[[], dict[int, ProcInfo]], poll_interval: float) -> None:
        self.proc = proc
        self.pgid = proc.pid  # start_new_session=True -> the child leads its own group
        self.send = send
        self.proc_table = proc_table
        self.poll_interval = poll_interval
        self.tracked: dict[int, int] = {}  # pid -> starttime
        self.signals_sent: list[str] = []

    def _refresh(self) -> dict[int, ProcInfo]:
        table = self.proc_table()
        for pid in descendants(self.proc.pid, table) | {self.proc.pid}:
            if pid in table:
                self.tracked.setdefault(pid, table[pid].starttime)
        return table

    def _live(self, table: dict[int, ProcInfo]) -> set[int]:
        group = {p for p, i in table.items() if i.pgrp == self.pgid and i.state not in _DEAD_STATES}
        tracked = {p for p, st in self.tracked.items()
                   if p in table and table[p].starttime == st and table[p].state not in _DEAD_STATES}
        return group | tracked

    def _signal_all(self, sig: int, table: dict[int, ProcInfo]) -> None:
        name = _signal_mod.Signals(sig).name
        try:
            self.send(-self.pgid, sig)
            self.signals_sent.append(f"{name}->group:{self.pgid}")
        except ProcessLookupError:
            pass
        for pid, st in self.tracked.items():
            info = table.get(pid)
            if info is None or info.starttime != st or info.state in _DEAD_STATES:
                continue  # gone, reused, or already dead: never signal
            if info.pgrp == self.pgid:
                continue  # already covered by the group signal
            try:
                self.send(pid, sig)
                self.signals_sent.append(f"{name}->pid:{pid}")
            except ProcessLookupError:
                pass

    def sweep(self, stages: tuple[tuple[int, float], ...]) -> list[int]:
        """Signal in stages until nothing is live. Returns survivors (empty on success)."""
        if self.pgid <= 1 or self.pgid == os.getpgrp():
            raise RuntimeError(f"refusing to signal process group {self.pgid} (not run-owned)")
        table = self._refresh()
        for sig, wait in stages:
            if not self._live(table):
                return []
            self._signal_all(sig, table)
            end = time.monotonic() + wait
            while True:
                self.proc.poll()  # reap the direct child so it does not linger as a zombie
                table = self._refresh()
                if not self._live(table):
                    return []
                if time.monotonic() >= end:
                    break
                time.sleep(self.poll_interval)
        return sorted(self._live(table))


def run_with_deadline(
    argv: list[str],
    *,
    input: Optional[bytes] = None,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    deadline: Optional[Deadline] = None,
    terminate_grace: float = 10.0,
    kill_wait: float = 5.0,
    drain_timeout: float = 5.0,
    poll_interval: float = 0.05,
    _signal: Callable[[int, int], None] = os.kill,
    _proc_table: Callable[[], dict[int, ProcInfo]] = read_proc_table,
) -> ProcessRunResult:
    """Run ``argv`` in a new session; enforce ``deadline`` by terminating the whole run-owned tree.

    ``deadline=None`` means no cap. Spawn errors propagate (the caller classifies them as a
    harness failure). Termination problems are reported as ``termination_failed``, never raised.
    """
    budget = deadline.budget_seconds if deadline is not None else None
    if deadline is not None and deadline.expired():
        return ProcessRunResult(termination=NOT_STARTED, timed_out=True, returncode=None,
                                elapsed_seconds=0.0, deadline_budget_seconds=budget)

    t0 = time.monotonic()
    proc = subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=cwd, env=env, start_new_session=True,
    )
    result = ProcessRunResult(termination=EXITED, timed_out=False, returncode=None,
                              pid=proc.pid, pgid=proc.pid, deadline_budget_seconds=budget)
    stages = ((_signal_mod.SIGTERM, terminate_grace), (_signal_mod.SIGKILL, kill_wait))
    terminator = _TreeTerminator(proc, _signal, _proc_table, poll_interval)

    try:
        out, err = proc.communicate(input=input,
                                    timeout=deadline.remaining() if deadline is not None else None)
    except subprocess.TimeoutExpired:
        result.timed_out = True
        result.termination = TIMEOUT_TERMINATED
        out, err = b"", b""
        try:
            result.survivors = terminator.sweep(stages)
        except Exception as exc:  # signal error, missing /proc, refusal: the harness lost control
            result.error = f"{type(exc).__name__}: {exc}"
        try:
            out, err = proc.communicate(timeout=drain_timeout)
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout or b""
            err = exc.stderr or b""
            result.error = result.error or "output pipes still held open after termination"
            for pipe in (proc.stdin, proc.stdout, proc.stderr):  # do not leak fds in the harness
                try:
                    if pipe is not None:
                        pipe.close()
                except OSError:
                    pass
        if result.survivors or result.error:
            result.termination = TERMINATION_FAILED
    else:
        # Exited on its own. Anything it left running in its group still belongs to the run.
        try:
            if terminator._live(terminator._refresh()):
                result.post_exit_swept = sorted(terminator._live(terminator.proc_table()))
                result.survivors = terminator.sweep(stages)
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
        if result.survivors or result.error:
            result.termination = TERMINATION_FAILED

    result.stdout, result.stderr = out or b"", err or b""
    result.raw_returncode = proc.returncode
    if proc.returncode is not None and proc.returncode < 0:
        result.signal = -proc.returncode
    # A harness-terminated process has no agent exit code of its own: never fabricate one.
    result.returncode = None if result.timed_out else proc.returncode
    result.elapsed_seconds = round(time.monotonic() - t0, 6)
    result.signals_sent = list(terminator.signals_sent)
    result.tracked_pids = sorted(terminator.tracked)
    return result
