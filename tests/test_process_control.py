"""G1: deadline enforcement and run-owned process-tree termination.

Written as ``unittest`` so it also runs under WSL's stdlib-only Python (no pytest there):

    PYTHONPATH=src python3 -m unittest tests.test_process_control -v

The POSIX tests spawn real local processes (no Claude, no network) and verify termination by
exact PID via ``/proc``; they are skipped where ``/proc`` does not exist (Windows).
"""

import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path

from codeagent_configlab.process_control import (
    EXITED,
    NOT_STARTED,
    TERMINATION_FAILED,
    TIMEOUT_TERMINATED,
    Deadline,
    run_with_deadline,
)

HAVE_PROC = os.name == "posix" and os.path.isdir("/proc/self")
PY = sys.executable
FAST = dict(terminate_grace=1.0, kill_wait=2.0, drain_timeout=2.0)


def _running(pid: int) -> bool:
    """True if ``pid`` exists and is not a zombie (exact PID, never by name)."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return raw[raw.rfind(")") + 2:].split()[0] not in ("Z", "X", "x")


def _wait_gone(pids, timeout=5.0) -> list:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        alive = [p for p in pids if _running(p)]
        if not alive:
            return []
        time.sleep(0.05)
    return [p for p in pids if _running(p)]


def _read_pids(path: Path, n: int, timeout=10.0) -> list:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists():
            parts = path.read_text().split()
            if len(parts) >= n:
                return [int(x) for x in parts[:n]]
        time.sleep(0.05)
    raise AssertionError(f"pid file {path} not written")


class FakeClock:
    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


class DeadlineTests(unittest.TestCase):
    """Test F (clock part): an absolute, shareable budget; platform independent."""

    def test_budget_is_shared_and_counts_down(self):
        clock = FakeClock()
        d = Deadline.start(30.0, clock=clock)
        self.assertEqual(d.remaining(), 30.0)
        clock.t += 12.5          # e.g. a C2 phase 1 consumed 12.5 s
        self.assertAlmostEqual(d.remaining(), 17.5)  # phase 2 would get only the remainder
        self.assertAlmostEqual(d.elapsed(), 12.5)
        self.assertFalse(d.expired())
        clock.t += 17.5
        self.assertEqual(d.remaining(), 0.0)
        self.assertTrue(d.expired())
        clock.t += 5
        self.assertEqual(d.remaining(), 0.0)  # never negative

    def test_rejects_non_numeric_or_open_budget(self):
        for bad in ("OPEN", None, True, 0, -1):
            with self.assertRaises((TypeError, ValueError)):
                Deadline.start(bad)


@unittest.skipUnless(HAVE_PROC, "needs Linux /proc")
class ProcessTreeTests(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g1-test-"))

    def test_a_normal_completion(self):
        res = run_with_deadline([PY, "-c", "print('hello-g1')"], deadline=Deadline.start(30), **FAST)
        self.assertEqual(res.termination, EXITED)
        self.assertFalse(res.timed_out)
        self.assertEqual(res.returncode, 0)
        self.assertIn(b"hello-g1", res.stdout)
        self.assertEqual(res.signals_sent, [])

    def test_a_no_deadline_means_no_cap(self):
        res = run_with_deadline([PY, "-c", "print('x')"], deadline=None, **FAST)
        self.assertEqual(res.termination, EXITED)
        self.assertIsNone(res.deadline_budget_seconds)

    def test_b_simple_timeout(self):
        res = run_with_deadline([PY, "-c", "import time; time.sleep(60)"],
                                deadline=Deadline.start(1.0), **FAST)
        self.assertEqual(res.termination, TIMEOUT_TERMINATED)
        self.assertTrue(res.timed_out)
        self.assertIsNone(res.returncode, "no fabricated exit code after harness termination")
        self.assertEqual(res.signal, signal.SIGTERM)
        self.assertEqual(res.survivors, [])
        self.assertLess(res.elapsed_seconds, 10)
        self.assertEqual(_wait_gone([res.pid]), [])

    def test_c_descendants_terminated(self):
        """Parent + grandchild ignoring SIGTERM + grandchild in its own session (like
        ``bwrap --new-session``) + a great-grandchild: every exact PID must be gone."""
        pidfile = self.tmp / "pids"
        script = r"""
import os, subprocess, sys, time
ign = "import signal, subprocess, sys, time\n" \
      "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" \
      "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n" \
      "open(sys.argv[1], 'w').write(str(g.pid))\n" \
      "time.sleep(300)\n"
ggfile = sys.argv[1] + ".gg"
g1 = subprocess.Popen([sys.executable, "-c", ign, ggfile])
g2 = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"], start_new_session=True)
while not os.path.exists(ggfile) or not open(ggfile).read():
    time.sleep(0.02)
gg = int(open(ggfile).read())
open(sys.argv[1], "w").write(f"{os.getpid()} {g1.pid} {g2.pid} {gg}\n")
time.sleep(300)
"""
        res = run_with_deadline([PY, "-c", script, str(pidfile)], deadline=Deadline.start(3.0), **FAST)
        pids = _read_pids(pidfile, 4)
        self.assertEqual(res.termination, TIMEOUT_TERMINATED, res.metadata())
        self.assertTrue(res.timed_out)
        self.assertEqual(res.survivors, [])
        # the escaped-session grandchild really was in another group, and was still tracked
        self.assertIn(pids[2], res.tracked_pids)
        self.assertTrue(any(s.startswith("SIGKILL") for s in res.signals_sent),
                        "SIGTERM-ignoring child must force escalation")
        self.assertEqual(_wait_gone(pids), [], f"descendants still running: {pids}")

    def test_d_termination_failure_is_reported_not_timeout(self):
        """Injected signal delivery that silently does nothing -> survivors -> termination_failed."""
        res = run_with_deadline([PY, "-c", "import time; time.sleep(60)"],
                                deadline=Deadline.start(0.5), terminate_grace=0.3, kill_wait=0.3,
                                drain_timeout=0.5, _signal=lambda pid, sig: None)
        try:
            self.assertEqual(res.termination, TERMINATION_FAILED)
            self.assertIn(res.pid, res.survivors)
            self.assertIsNotNone(res.error)
        finally:
            os.killpg(res.pgid, signal.SIGKILL)
            os.waitpid(res.pid, 0)

    def test_d_signal_error_is_reported(self):
        def boom(pid, sig):
            raise PermissionError("injected")
        res = run_with_deadline([PY, "-c", "import time; time.sleep(60)"],
                                deadline=Deadline.start(0.5), terminate_grace=0.3, kill_wait=0.3,
                                drain_timeout=0.5, _signal=boom)
        try:
            self.assertEqual(res.termination, TERMINATION_FAILED)
            self.assertIn("PermissionError", res.error)
        finally:
            os.killpg(res.pgid, signal.SIGKILL)
            os.waitpid(res.pid, 0)

    def test_d_missing_proc_is_reported(self):
        def no_proc():
            raise FileNotFoundError("/proc")
        res = run_with_deadline([PY, "-c", "import time; time.sleep(60)"],
                                deadline=Deadline.start(0.5), terminate_grace=0.3, kill_wait=0.3,
                                drain_timeout=0.5, _proc_table=no_proc)
        try:
            self.assertEqual(res.termination, TERMINATION_FAILED)
        finally:
            try:
                os.killpg(res.pgid, signal.SIGKILL)
                os.waitpid(res.pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass

    def test_e_partial_output_preserved(self):
        res = run_with_deadline(
            [PY, "-c", "import sys, time; print('BEFORE-CAP', flush=True); "
                       "print('ERR-BEFORE', file=sys.stderr, flush=True); time.sleep(60)"],
            deadline=Deadline.start(1.5), **FAST)
        self.assertEqual(res.termination, TIMEOUT_TERMINATED)
        self.assertIn(b"BEFORE-CAP", res.stdout)
        self.assertIn(b"ERR-BEFORE", res.stderr)

    def test_f_shared_deadline_across_sequential_invocations(self):
        d = Deadline.start(5.0)
        first = run_with_deadline([PY, "-c", "print('p1')"], deadline=d, **FAST)
        self.assertEqual(first.termination, EXITED)
        self.assertLess(d.remaining(), 5.0)
        second = run_with_deadline([PY, "-c", "print('p2')"], deadline=d, **FAST)
        self.assertEqual(second.termination, EXITED)

        spent = Deadline.start(0.5)
        slow = run_with_deadline([PY, "-c", "import time; time.sleep(30)"], deadline=spent, **FAST)
        self.assertEqual(slow.termination, TIMEOUT_TERMINATED)
        after = run_with_deadline([PY, "-c", "print('never')"], deadline=spent, **FAST)
        self.assertEqual(after.termination, NOT_STARTED)
        self.assertIsNone(after.pid, "nothing may be spawned once the shared budget is gone")
        self.assertIsNone(after.returncode)

    def test_g_leftover_group_members_swept_after_normal_exit(self):
        pidfile = self.tmp / "left"
        script = (
            "import subprocess, sys\n"
            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'],"
            " stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            "open(sys.argv[1], 'w').write(str(g.pid))\n"
        )
        res = run_with_deadline([PY, "-c", script, str(pidfile)], deadline=Deadline.start(30), **FAST)
        (left,) = _read_pids(pidfile, 1)
        self.assertEqual(res.termination, EXITED)
        self.assertEqual(res.returncode, 0)
        self.assertIn(left, res.post_exit_swept)
        self.assertEqual(_wait_gone([left]), [])


if __name__ == "__main__":
    unittest.main()
