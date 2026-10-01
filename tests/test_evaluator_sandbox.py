"""G5s: evaluator commands run under a dedicated sandbox-runtime policy (model-free).

Written as ``unittest`` so it runs under WSL's stdlib-only Python as ``cclab``:

    PYTHONPATH=src:tests python3 -m unittest tests.test_evaluator_sandbox -v

Pure policy tests run everywhere (also under the Windows pytest suite). Real-sandbox tests need
Linux + the pinned srt/node/bwrap and are skipped elsewhere. No Claude call, no network use, and
the real credential file is never opened (only ``stat``-ed from inside the sandbox).
"""

import inspect
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codeagent_configlab.artifacts import scan_for_secrets  # noqa: E402
from codeagent_configlab.envelope import DEFAULT_CREDENTIAL_PATH  # noqa: E402
from codeagent_configlab.hashing import sha256_text  # noqa: E402
from codeagent_configlab.evaluator_sandbox import (  # noqa: E402
    SYSTEM_READ_PATHS, EvaluatorSandboxPolicy, production_evaluator_sandbox)
from codeagent_configlab.status import Acceptance, Integrity, Regression  # noqa: E402
from codeagent_configlab.task_evaluator import CheckSpec, TaskEvaluator, TaskEvaluatorSpec  # noqa: E402

HOME = "/home/cclab"


def _pure_sandbox(**kw):
    spec = TaskEvaluatorSpec(pristine=Path("/srv/h/tasks/t/pristine"),
                             hidden_dir=Path("/srv/h/tasks/t/hidden"),
                             acceptance=(CheckSpec("a", ("python3", "-c", "pass")),),
                             regression=(CheckSpec("r", ("python3", "-c", "pass")),))
    return production_evaluator_sandbox(spec, harness_root="/srv/h", results_root="/srv/h/results",
                                        home=HOME, **kw)


class PolicyShapeTests(unittest.TestCase):
    """Pure: the rendered srt config and the policy identity (all platforms)."""

    def test_render_is_deny_all_with_minimal_allow(self):
        pol = _pure_sandbox().policy
        cfg = pol.render("/tmp/cclab-taskeval-1/wc", "/tmp/cclab-taskeval-1/home")
        fs, net = cfg["filesystem"], cfg["network"]
        self.assertEqual(fs["denyRead"][0], "/")
        self.assertIn("/tmp/claude/*", fs["denyRead"])
        self.assertEqual(fs["allowWrite"], ["/tmp/cclab-taskeval-1/wc", "/tmp/cclab-taskeval-1/home"])
        self.assertEqual(fs["denyWrite"], ["/tmp/claude"])
        self.assertEqual(fs["allowRead"], [*SYSTEM_READ_PATHS, pol.node_binary, pol.seccomp_helper,
                                           "/tmp/cclab-taskeval-1/wc", "/tmp/cclab-taskeval-1/home"])
        # only the single node binary, never its bin/ dir, HOME, the harness or /mnt/c
        self.assertTrue(pol.node_binary.endswith("/bin/node"))
        for p in fs["allowRead"]:
            self.assertFalse(p in (HOME, f"{HOME}/.claude", "/mnt/c", "/srv/h", "/home"), p)
        self.assertEqual(net, {"allowedDomains": [], "deniedDomains": []})
        self.assertNotIn("allowAllUnixSockets", json.dumps(cfg))

    def test_identity_lists_real_credential_structurally_and_has_no_per_run_paths(self):
        pol = _pure_sandbox().policy
        ident = pol.identity_dict()
        self.assertEqual(ident["read"]["explicit_deny"]["credential_path_sha256"],
                         sha256_text(DEFAULT_CREDENTIAL_PATH))
        self.assertIn(DEFAULT_CREDENTIAL_PATH, pol.protected_paths())   # rendered as explicit deny
        blob = json.dumps(ident)
        self.assertNotIn("cclab-taskeval", blob)
        self.assertEqual(scan_for_secrets(blob), [])                     # recordable in artifacts
        for role in ("harness_root", "pristine", "hidden_source", "results_root"):
            self.assertTrue(ident["read"]["explicit_deny"][role])
        self.assertEqual(pol.policy_hash(), _pure_sandbox().policy.policy_hash())   # stable
        self.assertEqual(len(pol.policy_hash()), 64)

    def test_r_policy_is_configuration_independent(self):
        params = inspect.signature(production_evaluator_sandbox).parameters
        self.assertFalse({"configuration", "config", "envelope", "manifest"} & set(params))
        fields = set(EvaluatorSandboxPolicy.__dataclass_fields__)
        self.assertFalse({"configuration", "envelope", "treatment"} & fields)
        hashes = {c: _pure_sandbox().policy.policy_hash() for c in ("C0", "C1", "C2")}
        self.assertEqual(len(set(hashes.values())), 1)

    def test_protected_path_inside_a_readable_tree_is_refused(self):
        with self.assertRaises(ValueError):
            EvaluatorSandboxPolicy(node_binary=f"{HOME}/n/bin/node", seccomp_helper=f"{HOME}/n/s",
                                   harness_root="/usr/share/harness", pristine="/srv/p",
                                   hidden_dir=None, results_root="/srv/r")

    def test_wrap_is_pure_argv(self):
        sb = _pure_sandbox()
        sb._config = "/tmp/cclab-taskeval-1/srt-eval.json"
        argv = sb.wrap(["python3", "-c", "print('a b; rm -rf ~')"], Path("/tmp/x"))
        self.assertEqual(argv, [sb.srt_path, "-s", sb._config, "--", "python3", "-c",
                                "print('a b; rm -rf ~')"])

    def test_prepare_refuses_off_linux(self):
        if sys.platform.startswith("linux"):
            self.skipTest("Linux host")
        from codeagent_configlab.evaluator_sandbox import EvaluatorSandboxError

        with self.assertRaises(EvaluatorSandboxError):
            _pure_sandbox().prepare(Path("r"), Path("r/wc"), Path("r/home"))


def _real_srt_available() -> bool:
    if not sys.platform.startswith("linux") or not os.path.isdir("/proc/self"):
        return False
    sb = _pure_sandbox()
    return all(os.path.exists(p) for p in (sb.srt_path, sb.policy.node_binary,
                                           sb.policy.seccomp_helper, "/usr/bin/bwrap"))


REAL = _real_srt_available()


def _cmdline_has(pid: str, needle: bytes) -> bool:
    try:
        return needle in Path(f"/proc/{pid}/cmdline").read_bytes() and int(pid) != os.getpid()
    except OSError:
        return False


@unittest.skipUnless(REAL, "needs Linux + pinned sandbox-runtime/node/bwrap (WSL as cclab)")
class RealSandboxMatrix(unittest.TestCase):
    """A-K, O, Q (+ mutation containment) from one full evaluation of the security fixture."""

    @classmethod
    def setUpClass(cls):
        from _evsec import EvsecLayout

        cls.L = EvsecLayout()
        cls.before = cls.L.protected_snapshot()
        cls.sb = cls.L.sandbox()
        cls.res = TaskEvaluator(cls.L.spec(), sandbox=cls.sb).evaluate(cls.L.candidate)
        time.sleep(0.3)
        cls.after = cls.L.protected_snapshot()
        cls.connections = cls.L.listener.connections

    @classmethod
    def tearDownClass(cls):
        cls.L.cleanup()

    def _py(self):
        from _evsec import parse_probe

        return parse_probe(self.res, "probe-py", "PROBE:")

    def test_a_sandbox_starts_and_all_checks_pass(self):
        self.assertFalse(self.res.evaluator_error, self.res.detail)
        self.assertEqual(self.res.sandbox["kind"], "srt")
        self.assertTrue(self.res.sandbox["production_safe"])
        for c in self.res.checks:
            self.assertEqual(c["status"], "pass", c)
        self.assertEqual((self.res.acceptance, self.res.regression), (Acceptance.PASS, Regression.PASS))

    def test_b_copy_read_write_tmp_and_children_work(self):
        from _evsec import EXPECT_ALLOWED

        m = self._py()
        for k in EXPECT_ALLOWED:
            self.assertTrue(m[k]["ok"], (k, m[k]))
        self.assertIs(m["tmp_write"]["detail"], True)            # TMPDIR = private evaluation home
        self.assertIs(m["hidden_injected_in_copy"]["detail"], True)

    def test_c_to_i_reads_and_network_blocked(self):
        from _evsec import EXPECT_BLOCKED_PREFIXES

        m = self._py()
        for k, v in m.items():
            if k.startswith(EXPECT_BLOCKED_PREFIXES):
                self.assertFalse(v["ok"], (k, v))
        for k in ("read:harness_canary", "read:hidden_source", "read:pristine", "read:results",
                  "read:fake_credential", "read:home_canary", "read:real_harness_repo",
                  "read:tmp_claude_canary", "read:other_eval_copy", "read:symlink_escape",
                  "net:local_listener", "net:unix_socket"):
            self.assertIn(k, m)
        self.assertEqual(self.connections, 0)                    # I: listener never reached

    def test_g_h_credentials_home_mnt_c_not_even_visible(self):
        m = self._py()
        for k in ("exists:real_credential", "exists:claude_dir", "exists:harness_root",
                  "exists:probe_root"):
            self.assertFalse(m[k]["ok"], k)
        home = m["listdir:home"]
        # only the node-binary mount skeleton, plus the probe's own plant in the private tmpfs
        self.assertTrue(not home["ok"] or set(home["detail"]) <= {".nvm", "EVAL_PLANTED.txt"}, home)
        mnt = m["listdir:mnt_c"]
        self.assertTrue(not mnt["ok"] or mnt["detail"] == [], mnt)
        tmp = m["listdir:tmp"]
        self.assertFalse(any("cclab-taskeval-other" in n for n in (tmp["detail"] if tmp["ok"] else [])))
        sub = m["listdir:tmp_claude_sub"]
        self.assertTrue(not sub["ok"] or sub["detail"] in ([], ["EVAL_PLANTED.txt"]), sub)
        run = m["listdir:run"]
        self.assertTrue(not run["ok"] or run["detail"] == [], run)   # no WSL interop sockets

    def test_node_probe_matches(self):
        from _evsec import parse_probe

        n = parse_probe(self.res, "probe-node", "NODEPROBE:")
        self.assertTrue(n["copy_write"]["ok"] and n["child_process"]["ok"], n)
        self.assertFalse(n["net:local_listener"]["ok"], n)
        for k, v in n.items():
            if k.startswith("read:"):
                self.assertFalse(v["ok"], (k, v))

    def test_j_k_f_mutation_containment_exact_hashes(self):
        self.assertEqual(self.before, self.after)

    def test_k_hidden_material_never_reaches_canonical_state(self):
        from _evsec import HIDDEN_CANARY

        self.assertFalse((self.L.candidate / "_hidden_tests").exists())
        for p in self.L.candidate.rglob("*"):
            if p.is_file() and not p.is_symlink():
                self.assertNotIn(HIDDEN_CANARY.encode(), p.read_bytes(), p)
        self.assertNotIn(HIDDEN_CANARY, json.dumps(self.res.to_dict()))

    def test_q_structural_checks_ran_in_the_same_sandbox(self):
        kinds = {c["name"]: (c["kind"], c["status"]) for c in self.res.checks}
        self.assertEqual(kinds["struct-node"], ("structural", "pass"))
        self.assertEqual(kinds["struct-py"], ("structural", "pass"))
        self.assertEqual(kinds["node-test-child"], ("regression", "pass"))

    def test_policy_record(self):
        rec = self.res.sandbox
        self.assertEqual(rec["policy_hash"], self.sb.policy.policy_hash())
        self.assertEqual(rec["identity"]["read"]["explicit_deny"]["credential_path_sha256"],
                         sha256_text(str(self.L.fake_cred)))
        self.assertNotIn("FAKE-CRED-CANARY", json.dumps(rec))


@unittest.skipUnless(REAL, "needs Linux + pinned sandbox-runtime/node/bwrap (WSL as cclab)")
class RealSandboxBehaviour(unittest.TestCase):
    def setUp(self):
        from _evsec import EvsecLayout

        self.L = EvsecLayout()

    def tearDown(self):
        self.L.cleanup()

    def _eval(self, spec=None, sandbox=None, candidate=None):
        return TaskEvaluator(spec or self.L.spec(), sandbox=sandbox or self.L.sandbox()).evaluate(
            candidate or self.L.candidate)

    def test_l_timeout_kills_the_whole_sandboxed_tree(self):
        marker = f"g5s-grandchild-{uuid.uuid4().hex}"
        code = ("import signal, subprocess, sys, time\n"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                "subprocess.Popen([sys.executable, '-c', 'import signal,time;"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)', "
                f"'{marker}'], start_new_session=True)\n"
                "time.sleep(300)\n")
        hang = CheckSpec("hang", ("python3", "-c", code, marker), 2.0)
        t0 = time.monotonic()
        r = self._eval(spec=self.L.spec(acceptance=(hang,)))
        c = next(c for c in r.checks if c["name"] == "hang")
        self.assertEqual((c["status"], c["timed_out"]), ("fail", True))
        self.assertFalse(r.evaluator_error, r.detail)          # task outcome, harness in control
        self.assertEqual(r.acceptance, Acceptance.FAIL)
        self.assertLess(time.monotonic() - t0, 60)
        time.sleep(0.5)
        alive = []
        for pid in filter(str.isdigit, os.listdir("/proc")):
            try:
                if marker.encode() in Path(f"/proc/{pid}/cmdline").read_bytes():
                    alive.append(pid)
            except OSError:
                pass
        self.assertEqual(alive, [])

    def test_m_n_broken_runtime_is_evaluator_error_never_rerun_unsandboxed(self):
        tmp = Path(tempfile.mkdtemp(prefix="g5s-fake-srt-"))
        try:
            log = tmp / "calls.log"
            fake = tmp / "srt"
            fake.write_text(f"#!/bin/sh\necho call >> {log}\necho 'Error: sandbox init failed' >&2\n"
                            "exit 1\n")
            fake.chmod(0o755)
            marker = tmp / "RAN_UNSANDBOXED"
            check = CheckSpec("marker", ("python3", "-c", f"open({str(marker)!r},'w').write('x')"), 30)
            r = self._eval(spec=self.L.spec(acceptance=(check,)),
                           sandbox=self.L.sandbox(srt_path=str(fake)))
            self.assertTrue(r.evaluator_error)
            self.assertEqual((r.acceptance, r.regression), (Acceptance.ERROR, Regression.ERROR))
            self.assertIn("preflight failed", r.detail)
            self.assertIn("sandbox init failed", r.detail)       # diagnostics preserved
            self.assertFalse(marker.exists())
            self.assertEqual(log.read_text().count("call"), 1)   # preflight only, no retry
            # policy/runtime path missing -> initialization error before anything runs
            sb = self.L.sandbox()
            object.__setattr__(sb, "policy", EvaluatorSandboxPolicy(
                **{**sb.policy.__dict__, "node_binary": "/nonexistent/bin/node"}))
            r2 = self._eval(sandbox=sb)
            self.assertTrue(r2.evaluator_error)
            self.assertIn("initialization failed", r2.detail)
            # no sandbox at all
            r3 = TaskEvaluator(self.L.spec(acceptance=(check,))).evaluate(self.L.candidate)
            self.assertTrue(r3.evaluator_error)
            self.assertFalse(marker.exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_g8_mid_run_srt_failure_is_evaluator_error_not_task_fail(self):
        """srt dies for one check after a good preflight: that check is an evaluator error, the
        control check that really exits 1 inside the sandbox stays a task fail (G8)."""
        tmp = Path(tempfile.mkdtemp(prefix="g8-srt-"))
        try:
            real = self.L.sandbox().srt_path
            wrapper = tmp / "srt"
            wrapper.write_text("#!/bin/sh\n"
                               'case "$*" in *CCLAB-EVAL-RC*MIDRUN*) '
                               'echo "Error: simulated srt failure" >&2; exit 1;; esac\n'
                               f'exec "{real}" "$@"\n')
            wrapper.chmod(0o755)
            marker = tmp / "RAN_UNSANDBOXED"
            midrun = CheckSpec("midrun", ("python3", "-c",
                                          f"open({str(marker)!r},'w').write('x'); raise SystemExit(1)  # MIDRUN"), 30)
            control = CheckSpec("control", ("python3", "-c", "raise SystemExit(1)"), 30)
            t0 = time.monotonic()
            r = self._eval(spec=self.L.spec(acceptance=(midrun,), structural=(), regression=(control,)),
                           sandbox=self.L.sandbox(srt_path=str(wrapper)))
            by = {c["name"]: c for c in r.checks}
            self.assertEqual(by["midrun"]["status"], "error")
            self.assertIn("did not attest", by["midrun"]["reason"])
            self.assertEqual(by["control"]["status"], "fail")         # real in-sandbox exit 1
            self.assertTrue(r.evaluator_error)
            self.assertEqual((r.acceptance, r.regression), (Acceptance.ERROR, Regression.FAIL))
            self.assertFalse(marker.exists())                          # never run unsandboxed
            self.assertLess(time.monotonic() - t0, 60)
            alive = [pid for pid in filter(str.isdigit, os.listdir("/proc"))
                     if _cmdline_has(pid, b"MIDRUN")]
            self.assertEqual(alive, [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_o_p_ordinary_failures_stay_task_failures(self):
        (self.L.candidate / "app.py").write_text("def add(a, b):\n    return a - b\n")
        r = self._eval(spec=self.L.spec(acceptance=(CheckSpec("hidden-accept", (
            "python3", "_hidden_tests/check_hidden.py"), 60),), structural=()))
        self.assertFalse(r.evaluator_error, r.detail)
        self.assertEqual(r.regression, Regression.FAIL)          # public test catches it
        acc = CheckSpec("accept-fails", ("python3", "-c", "raise SystemExit(1)"), 60)
        r2 = self._eval(spec=self.L.spec(acceptance=(acc,), structural=(),
                                         regression=(CheckSpec("ok", ("python3", "-c", "pass")),)))
        self.assertFalse(r2.evaluator_error, r2.detail)
        self.assertEqual((r2.acceptance, r2.regression), (Acceptance.FAIL, Regression.PASS))

    def test_g5_protected_restore_flag_inject_through_real_sandbox(self):
        (self.L.candidate / "tests" / "test_public.py").write_text("assert True\n")
        (self.L.candidate / "app.py").write_text("def add(a, b):\n    return 0\n")
        before = (self.L.candidate / "tests" / "test_public.py").read_text()
        r = self._eval(spec=self.L.spec(acceptance=(CheckSpec("hidden-accept", (
            "python3", "_hidden_tests/check_hidden.py"), 60),), structural=()))
        self.assertFalse(r.evaluator_error, r.detail)
        self.assertEqual(r.integrity, Integrity.PROTECTED_PATH_MODIFIED)
        self.assertEqual(r.regression, Regression.FAIL)          # restored public test ran
        self.assertIn("check_hidden.py", r.injected)
        self.assertEqual((self.L.candidate / "tests" / "test_public.py").read_text(), before)
        self.assertFalse((self.L.candidate / "_hidden_tests").exists())

    def test_r_c0_c1_c2_lifecycle_evaluator_policy_identical(self):
        from _helpers import TEST_STATEMENT, make_treated_manifest, make_treatment

        from codeagent_configlab.envelope import implementation_envelope
        from codeagent_configlab.lifecycle import AgentRunOutcome, DryCleanupRunner, RunLifecycle
        from codeagent_configlab.session import SessionSpec
        from codeagent_configlab.status import AgentOutcome

        class Agent:
            def run(self, working_copy, envelope, session, *, prompt=None, deadline=None):
                sid = session.session_id
                return AgentRunOutcome(exit_code=0, session_id=sid,
                                       agent_outcome=AgentOutcome.COMPLETED, stdout="",
                                       events=[{"type": "system", "subtype": "init", "session_id": sid},
                                               {"type": "result", "session_id": sid}])

        home = self.L.root / "lifehome"
        (home / ".claude" / "projects").mkdir(parents=True)
        spec = self.L.spec(acceptance=(CheckSpec("hidden-accept", (
            "python3", "_hidden_tests/check_hidden.py"), 60),), structural=())
        hashes = {}
        for conf in ("C0", "C1", "C2"):
            life = RunLifecycle(pristine=self.L.pristine, runs_root=self.L.harness / f"runs-{conf}",
                                results_root=self.L.results, home=home)
            m = make_treated_manifest(conf)
            res = life.execute(manifest=m, envelope=implementation_envelope(conf),
                               session=SessionSpec("new", str(uuid.uuid4())),
                               evaluator=TaskEvaluator(spec, sandbox=self.L.sandbox()),
                               agent_runner=Agent(), cleanup_runner=DryCleanupRunner(),
                               treatment=make_treatment(conf), task_statement=TEST_STATEMENT)
            ev = json.loads((self.L.results / m.run_id / "evaluator.json").read_text())
            self.assertFalse(ev["evaluator_error"], ev["detail"])
            hashes[conf] = ev["sandbox"]["policy_hash"]
        self.assertEqual(len(set(hashes.values())), 1, hashes)


if __name__ == "__main__":
    unittest.main()
