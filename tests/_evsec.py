"""G5s evaluator-security probe layout (model-free). Shared by the WSL tests and the spike report.

Builds a throwaway layout under the real HOME that mirrors the production topology:

    ~/cclab-g5s-probe-<nonce>/
        harness/                     simulated harness root (HARNESS canary)
            tasks/evsec/pristine     pristine fixture (source of truth)
            tasks/evsec/hidden       hidden tests (source of truth, HIDDEN canary)
            results/prev/…           a previous run's results (RESULTS canary)
            runs/wc-<nonce>/         canonical final-agent state (the candidate)
        fakehome/.claude/.credentials.json   FAKE credential canary (never a real secret)
        home-canary.txt              unrelated HOME content
    /tmp/cclab-taskeval-other-*/secret.txt   another evaluation's copy
    /tmp/claude/g5s-canary-<nonce>.txt       state shared with agent runs

The real credential (``/home/cclab/.claude/.credentials.json``) is only ever *stat*-ed from inside
the sandbox, never opened by anything here.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from codeagent_configlab.envelope import DEFAULT_CREDENTIAL_PATH
from codeagent_configlab.task_evaluator import CheckSpec, TaskEvaluatorSpec, overlay_candidate

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "fixtures" / "evaluator-security"
HIDDEN_CANARY = "HIDDEN-EVSEC-CANARY-7f3a91"
TMP_CLAUDE = Path("/tmp/claude")


def snapshot(root: Path) -> dict:
    """Exact state of a tree: every entry's type and content hash / link target."""
    snap = {}
    if not root.exists() and not root.is_symlink():
        return {"<absent>": True}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in sorted(dirnames + filenames):
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                snap[rel] = "link:" + os.readlink(p)
            elif p.is_file():
                snap[rel] = "file:" + hashlib.sha256(p.read_bytes()).hexdigest()
            else:
                snap[rel] = "dir"
    return snap


class Listener:
    """A harmless local TCP listener; records whether anything connected."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.connections = 0
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
                self.connections += 1
                conn.close()
            except OSError:
                continue

    def close(self):
        self._stop = True
        self._t.join(timeout=2)
        self.sock.close()


@dataclass
class EvsecLayout:
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def __post_init__(self):
        n = self.nonce
        self.root = Path.home() / f"cclab-g5s-probe-{n}"
        self.harness = self.root / "harness"
        self.pristine = self.harness / "tasks" / "evsec" / "pristine"
        self.hidden = self.harness / "tasks" / "evsec" / "hidden"
        self.results = self.harness / "results"
        self.candidate = self.harness / "runs" / f"wc-{n}"
        self.fake_cred = self.root / "fakehome" / ".claude" / ".credentials.json"
        self.home_canary = self.root / "home-canary.txt"
        self.harness_canary = self.harness / "HARNESS-CANARY.txt"
        self.results_canary = self.results / "prev" / "evaluator.json"
        self.other_eval = Path(tempfile.mkdtemp(prefix="cclab-taskeval-other-"))
        self.other_secret = self.other_eval / "wc" / "secret.txt"
        self.tmp_claude_canary = TMP_CLAUDE / f"g5s-canary-{n}.txt"
        self.listener = None

        shutil.copytree(FIXTURE / "pristine", self.pristine)
        shutil.copytree(FIXTURE / "hidden", self.hidden)
        self.harness_canary.write_text("HARNESS-CANARY\n")
        self.results_canary.parent.mkdir(parents=True)
        self.results_canary.write_text('{"RESULTS-CANARY": true}\n')
        self.fake_cred.parent.mkdir(parents=True)
        self.fake_cred.write_text('{"FAKE-CRED-CANARY": "not-a-real-token"}\n')
        self.home_canary.write_text("HOME-CANARY\n")
        self.other_secret.parent.mkdir(parents=True)
        self.other_secret.write_text("OTHER-EVAL-CANARY\n")
        TMP_CLAUDE.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.tmp_claude_canary.write_text("TMPCLAUDE-CANARY\n")

        self.candidate.parent.mkdir(parents=True)
        overlay_candidate(self.pristine, FIXTURE / "candidate", self.candidate)
        os.symlink(str(self.home_canary), self.candidate / "escape_link")
        self.listener = Listener()
        (self.candidate / "targets.json").write_text(json.dumps(self.targets(), indent=1))

    # ------------------------------------------------------------------ probes --
    def targets(self) -> dict:
        pid = os.getpid()
        uid_sub = str(TMP_CLAUDE / f"claude-{os.getuid()}")
        readable = {
            "harness_canary": str(self.harness_canary),
            "hidden_source": str(self.hidden / "check_hidden.py"),
            "pristine": str(self.pristine / "app.py"),
            "results": str(self.results_canary),
            "fake_credential": str(self.fake_cred),
            "home_canary": str(self.home_canary),
            "other_eval_copy": str(self.other_secret),
            "tmp_claude_canary": str(self.tmp_claude_canary),
            "real_harness_repo": str(REPO_ROOT / "src" / "codeagent_configlab" / "__init__.py"),
            "symlink_escape": "escape_link",
            "proc1_root": f"/proc/1/root{self.harness_canary}",
            "proc_harness_root": f"/proc/{pid}/root{self.harness_canary}",
            "proc_harness_environ": f"/proc/{pid}/environ",
        }
        return {
            "read": readable,
            "append": {k: readable[k] for k in ("harness_canary", "hidden_source", "pristine",
                                                "results", "fake_credential", "home_canary",
                                                "other_eval_copy", "tmp_claude_canary",
                                                "symlink_escape")}
                      | {"canonical_candidate": str(self.candidate / "app.py")},
            "create_in": {"harness": str(self.harness), "results": str(self.results),
                          "pristine": str(self.pristine), "hidden": str(self.hidden),
                          "canonical_candidate": str(self.candidate), "home": str(Path.home()),
                          "tmp_claude": str(TMP_CLAUDE), "tmp_claude_sub": uid_sub,
                          "tmp": "/tmp"},
            "listdir": {"home": str(Path.home()), "mnt_c": "/mnt/c", "tmp": "/tmp",
                        "tmp_claude_sub": uid_sub, "run": "/run"},
            "exists": {"real_credential": DEFAULT_CREDENTIAL_PATH,
                       "claude_dir": str(Path.home() / ".claude"),
                       "harness_root": str(self.harness), "probe_root": str(self.root)},
            "port": self.listener.port,
        }

    def spec(self, **overrides) -> TaskEvaluatorSpec:
        base = dict(
            pristine=self.pristine, hidden_dir=self.hidden,
            protected_paths=("tests/test_public.py",),
            acceptance=(CheckSpec("probe-py", ("python3", "probe.py"), 60),
                        CheckSpec("probe-node", ("node", "probe.mjs"), 60),
                        CheckSpec("hidden-accept", ("python3", "_hidden_tests/check_hidden.py"), 60)),
            structural=(CheckSpec("struct-node", ("node", "_hidden_tests/structural_check.mjs"), 60),
                        CheckSpec("struct-py", ("python3", "-c",
                                                "import ast; ast.parse(open('app.py').read())"), 60)),
            regression=(CheckSpec("public", ("python3", "tests/test_public.py"), 60),
                        CheckSpec("node-test-child", ("node", "--test",
                                                      "_hidden_tests/child.test.mjs"), 60)),
        )
        base.update(overrides)
        return TaskEvaluatorSpec(**base)

    def sandbox(self, **kw):
        from codeagent_configlab.evaluator_sandbox import production_evaluator_sandbox

        return production_evaluator_sandbox(self.spec(), harness_root=str(self.harness),
                                            results_root=str(self.results),
                                            credential_path=str(self.fake_cred), **kw)

    def protected_snapshot(self) -> dict:
        tmp_claude_top = {p.name: (p.read_bytes() if p.is_file() and not p.is_symlink() else "?")
                          for p in TMP_CLAUDE.iterdir()} if TMP_CLAUDE.is_dir() else {}
        return {"probe_root": snapshot(self.root), "other_eval": snapshot(self.other_eval),
                "tmp_claude_top": {k: str(v) for k, v in tmp_claude_top.items()},
                "tmp_claude_sub": snapshot(TMP_CLAUDE / f"claude-{os.getuid()}")}

    def cleanup(self):
        if self.listener is not None:
            self.listener.close()
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.other_eval, ignore_errors=True)
        for p in (self.tmp_claude_canary, TMP_CLAUDE / "EVAL_PLANTED.txt"):
            if p.exists():
                p.unlink()


def parse_probe(result, check_name: str, prefix: str) -> dict:
    check = next(c for c in result.checks if c["name"] == check_name)
    line = next(l for l in check["stdout_tail"].splitlines() if l.startswith(prefix))
    return json.loads(line[len(prefix):])


# What must hold for the Python probe matrix. Reads and network must fail. Writes ("append:",
# "create_in:") into hidden locations may *succeed inside the sandbox* -- srt's read-deny tmpfs is
# writable -- but must never reach the host; that is proven by exact host snapshots, not by errno.
EXPECT_ALLOWED = ("copy_write", "copy_read", "tmp_write", "child_process", "hidden_injected_in_copy")
EXPECT_BLOCKED_PREFIXES = ("read:", "net:")
PY = sys.executable
