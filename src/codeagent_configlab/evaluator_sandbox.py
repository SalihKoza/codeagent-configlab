"""Evaluator sandbox (G5s): run task check commands under a dedicated sandbox-runtime policy.

Threat model: agent-written repository code is **untrusted** while evaluator checks execute. The
evaluator sandbox is a separate trust boundary from the Candidate-2 agent sandbox and shares none
of its settings: no Claude state, no network, no AF_UNIX, and a read view that is *deny-all* with a
small explicit allow list.

Topology (harness Python is never loaded inside the sandbox)::

    harness (outside): copy -> restore protected paths -> inject hidden tests
      run_with_deadline([srt, -s, <root>/srt-eval.json, --, *check.argv], cwd=<root>/wc)
        srt (node, outside) -> sh -> bwrap --new-session --unshare-pid/net/user -> check command

What the command sees (srt 0.0.77, verified on WSL, ``docs/G5S_EVALUATOR_SANDBOX.md``):

* read/write: the evaluator copy ``<root>/wc`` and its private HOME/TMPDIR ``<root>/home``;
* read-only: :data:`SYSTEM_READ_PATHS`, the pinned ``node`` binary (the single file, not its
  ``bin/`` directory), and srt's own seccomp helper binary (required to apply the AF_UNIX filter);
* everything else is hidden (``denyRead: ["/"]``): HOME (``~/.claude``, credentials, nvm), the
  harness root, pristine/hidden/reference sources, results, other evaluator copies, ``/mnt``,
  ``/run`` (WSL interop). ``/tmp/claude`` is always bound by srt itself; its entries are
  read-denied (``/tmp/claude/*``) and the directory is write-denied, so nothing can be read from
  or written into state shared with agent runs;
* network: none (``--unshare-net``); AF_UNIX socket creation blocked by srt's seccomp filter.

Initialization failures raise :class:`EvaluatorSandboxError`; the task evaluator turns them into
``evaluator_error`` and never re-runs a check without the sandbox (fail closed).

The policy identity (:meth:`EvaluatorSandboxPolicy.identity_dict`) is built from the task layout
and the pinned toolchain only -- never from the configuration -- so C0, C1 and C2 of one task are
evaluated under the same, hashable policy.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional

from .envelope import DEFAULT_CREDENTIAL_PATH
from .hashing import canonical_json_hash, sha256_text
from .manifest import NODE_VERSION, SANDBOX_RUNTIME_VERSION

EVALUATOR_SANDBOX_VERSION = "g5s-v2"   # v2 (G8): per-check exit-status launcher
CHECK_LAUNCHER = "sh-exit-trailer-v1"
SRT_CONFIG_NAME = "srt-eval.json"

# Read-only system locations a Python/Node check needs (interpreters, stdlib, shared libraries,
# loader cache, /bin/sh). Narrowest set verified to run python3, node and `node --test`.
SYSTEM_READ_PATHS: tuple[str, ...] = ("/usr", "/bin", "/lib", "/lib64", "/etc")
SANDBOX_PATH_TAIL: tuple[str, ...] = ("/usr/local/bin", "/usr/bin", "/bin")
PYTHON_BINARY = "/usr/bin/python3"
# srt binds /tmp/claude writable whatever the policy says; it is shared with agent runs.
TMP_CLAUDE = "/tmp/claude"

_SECCOMP_ARCH = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}


class EvaluatorSandboxError(RuntimeError):
    """The evaluator sandbox could not be initialized. Always an evaluator error, never a verdict."""


def _is_at_or_under(path: str, root: str) -> bool:
    p, r = PurePosixPath(path), PurePosixPath(root)
    return p == r or r in p.parents


@dataclass(frozen=True)
class EvaluatorSandboxPolicy:
    """The evaluator's srt policy. Config-independent; identity excludes per-evaluation paths."""

    node_binary: str
    seccomp_helper: str
    harness_root: str
    pristine: str
    hidden_dir: Optional[str]
    results_root: str
    credential_path: str = DEFAULT_CREDENTIAL_PATH
    python_binary: str = PYTHON_BINARY
    srt_version: str = SANDBOX_RUNTIME_VERSION
    system_read_paths: tuple[str, ...] = SYSTEM_READ_PATHS
    hidden_roots: tuple[str, ...] = ("/mnt/c",)

    def __post_init__(self):
        for name in ("node_binary", "seccomp_helper", "harness_root", "pristine", "results_root",
                     "credential_path", "python_binary"):
            if not PurePosixPath(getattr(self, name)).is_absolute():
                raise ValueError(f"evaluator sandbox path {name} must be absolute")
        for p in self.protected_paths():
            for allowed in (*self.system_read_paths, self.node_binary, self.seccomp_helper):
                if _is_at_or_under(p, allowed):   # a readable tree would re-expose it
                    raise ValueError(f"protected path {p!r} lies inside readable {allowed!r}")

    # ------------------------------------------------------------------ identity --
    def protected_paths(self) -> list[str]:
        """Explicitly named hidden locations (belt-and-braces on top of ``denyRead: ["/"]``)."""
        paths = [self.harness_root, self.pristine, self.results_root, self.credential_path]
        if self.hidden_dir:
            paths.append(self.hidden_dir)
        return paths + list(self.hidden_roots)

    def identity_dict(self) -> dict:
        return {
            "version": EVALUATOR_SANDBOX_VERSION,
            "runtime": "sandbox-runtime",
            "srt_version": self.srt_version,
            "network": {"allowed_domains": [], "allow_unix_sockets": False},
            "read": {
                "deny": "/",
                "allow_system": list(self.system_read_paths),
                "allow_toolchain": [self.node_binary, self.seccomp_helper],
                "allow_roles": ["evaluation_copy", "evaluation_home"],
                "explicit_deny": {
                    "harness_root": self.harness_root,
                    "pristine": self.pristine,
                    "hidden_source": self.hidden_dir,
                    "results_root": self.results_root,
                    # the path by hash only: artifacts refuse credential-file names (secret scan)
                    "credential_path_sha256": sha256_text(self.credential_path),
                    "hidden_roots": list(self.hidden_roots),
                    "tmp_claude_entries": f"{TMP_CLAUDE}/*",
                },
            },
            "write": {"allow_roles": ["evaluation_copy", "evaluation_home"], "deny": [TMP_CLAUDE]},
            "toolchain": {"python": self.python_binary, "node": self.node_binary},
            "path": self.sandbox_path(),
            "check_launcher": CHECK_LAUNCHER,
        }

    def policy_hash(self) -> str:
        return canonical_json_hash(self.identity_dict())

    # ----------------------------------------------------------------- rendering --
    def sandbox_path(self) -> str:
        return ":".join([str(PurePosixPath(self.node_binary).parent), *SANDBOX_PATH_TAIL])

    def render(self, work: str, home: str) -> dict:
        """The srt settings for one evaluation copy.

        Explicit denies are listed only if they exist: every one is already hidden by the ``/``
        deny, and srt may create mount-point stubs for absent paths.
        """
        explicit = [p for p in self.protected_paths() if os.path.lexists(p)]
        return {
            "network": {"allowedDomains": [], "deniedDomains": []},
            "filesystem": {
                "denyRead": ["/", *explicit, f"{TMP_CLAUDE}/*"],
                "allowRead": [*self.system_read_paths, self.node_binary, self.seccomp_helper,
                              work, home],
                "allowWrite": [work, home],
                "denyWrite": [TMP_CLAUDE],
            },
        }


SRT_PACKAGE_REL = "lib/node_modules/@anthropic-ai/sandbox-runtime"


def seccomp_helper_for(node_root: str) -> str:
    """srt's vendored seccomp helper for this CPU in the pinned nvm install (pure, no I/O)."""
    arch = _SECCOMP_ARCH.get(platform.machine().lower(), platform.machine().lower())
    return f"{node_root}/{SRT_PACKAGE_REL}/vendor/seccomp/{arch}/apply-seccomp"


@dataclass
class SrtEvaluatorSandbox:
    """The production evaluator sandbox: the ``command_wrapper`` seam of :class:`TaskEvaluator`."""

    policy: EvaluatorSandboxPolicy
    srt_path: str
    _config: Optional[str] = field(default=None, init=False, repr=False)
    _home: Optional[str] = field(default=None, init=False, repr=False)
    _srt_tmp: Optional[str] = field(default=None, init=False, repr=False)

    production_safe = True

    def prepare(self, root: Path, work: Path, home: Path) -> None:
        """Validate the host and write this evaluation's srt config. Raises EvaluatorSandboxError."""
        if not sys.platform.startswith("linux") or not os.path.isdir("/proc/self"):
            raise EvaluatorSandboxError("the evaluator sandbox requires Linux with /proc (WSL)")
        pol = self.policy
        for label, path in (("srt", self.srt_path), ("node", pol.node_binary),
                            ("seccomp helper", pol.seccomp_helper), ("python", pol.python_binary)):
            if not os.path.isfile(path) or not os.access(path, os.X_OK):
                raise EvaluatorSandboxError(f"{label} not found or not executable: {path}")
        if shutil.which("bwrap", path="/usr/bin:/bin") is None:
            raise EvaluatorSandboxError("bubblewrap (bwrap) not found")
        observed = self._srt_version()
        if observed != pol.srt_version:
            raise EvaluatorSandboxError(f"sandbox-runtime {observed} != pinned {pol.srt_version}")
        work_s, home_s = str(work), str(home)
        for p in pol.protected_paths():
            for mine in (str(root), work_s, home_s):
                if _is_at_or_under(mine, p) or _is_at_or_under(p, mine):
                    raise EvaluatorSandboxError(f"evaluation root {mine} overlaps protected {p}")
        try:
            Path(TMP_CLAUDE).mkdir(mode=0o700, parents=True, exist_ok=True)  # srt binds it
            srt_tmp = Path(root) / "srt-tmp"      # srt's own sockets: outside the sandbox view
            srt_tmp.mkdir(exist_ok=True)
            cfg = Path(root) / SRT_CONFIG_NAME    # <root> itself is not readable inside
            cfg.write_text(json.dumps(pol.render(work_s, home_s), indent=1), encoding="utf-8")
        except OSError as exc:
            raise EvaluatorSandboxError(f"cannot stage sandbox config: {exc}") from exc
        self._config, self._home, self._srt_tmp = str(cfg), home_s, str(srt_tmp)

    def _srt_version(self) -> str:
        # the pinned package the policy's seccomp helper belongs to: <pkg>/vendor/seccomp/<arch>/x
        pkg = Path(self.policy.seccomp_helper).parents[3] / "package.json"
        try:
            return str(json.loads(pkg.read_text(encoding="utf-8")).get("version"))
        except (OSError, ValueError) as exc:
            raise EvaluatorSandboxError(f"cannot read sandbox-runtime version: {exc}") from exc

    def wrap(self, argv: list[str], cwd: Path) -> list[str]:
        if self._config is None:
            raise EvaluatorSandboxError("sandbox not prepared")
        return [self.srt_path, "-s", self._config, "--", *argv]

    def wrap_check(self, argv: list[str], cwd: Path, nonce: str) -> list[str]:
        """A task check, run through the fixed in-sandbox launcher that attests its exit status
        (G8). A missing/mismatched attestation is an evaluator error, never a task verdict."""
        from .task_evaluator import SH_CHECK_LAUNCHER

        return self.wrap(["/bin/sh", "-c", SH_CHECK_LAUNCHER, "sh", nonce, *argv], cwd)

    def env(self) -> dict:
        """Environment overrides: fixed PATH; child TMPDIR = private HOME; srt's own TMPDIR hidden."""
        return {"PATH": self.policy.sandbox_path(), "CLAUDE_CODE_TMPDIR": self._home,
                "TMPDIR": self._srt_tmp}

    def resolve_program(self, argv0: str, work: Path) -> str:
        """Absolute path the preflight must find executable inside the sandbox."""
        if "/" in argv0:
            return argv0 if argv0.startswith("/") else str(Path(work) / argv0)
        found = shutil.which(argv0, path=self.policy.sandbox_path())
        if found is None:
            raise EvaluatorSandboxError(f"check program {argv0!r} not found on the sandbox PATH")
        return found

    def preflight_argv(self, programs: list[str], nonce: str) -> list[str]:
        script = ('for p; do test -x "$p" || { echo "missing:$p"; exit 3; }; done; '
                  f'echo {nonce}')
        return ["/bin/sh", "-c", script, "sh", *programs]

    def record(self) -> dict:
        return {"kind": "srt", "version": EVALUATOR_SANDBOX_VERSION,
                "policy_hash": self.policy.policy_hash(), "identity": self.policy.identity_dict(),
                "production_safe": True}


def production_evaluator_sandbox(spec, *, harness_root: str, results_root: str,
                                 home: str = "/home/cclab",
                                 credential_path: str = DEFAULT_CREDENTIAL_PATH,
                                 srt_path: Optional[str] = None) -> SrtEvaluatorSandbox:
    """The one evaluator sandbox for a task. Deliberately takes **no configuration**: C0/C1/C2
    of the same task get an identical policy (and hash).

    ``srt_path`` overrides only the launcher (tests use it to simulate a broken runtime); the
    seccomp helper is always the pinned install's, so the policy identity does not change.
    """
    node_root = f"{home}/.nvm/versions/node/v{NODE_VERSION}"
    pinned_srt = f"{node_root}/bin/srt"
    policy = EvaluatorSandboxPolicy(
        node_binary=f"{node_root}/bin/node",
        seccomp_helper=seccomp_helper_for(node_root),
        harness_root=Path(harness_root).as_posix(),
        pristine=Path(spec.pristine).as_posix(),
        hidden_dir=Path(spec.hidden_dir).as_posix() if spec.hidden_dir is not None else None,
        results_root=Path(results_root).as_posix(),
        credential_path=credential_path,
    )
    return SrtEvaluatorSandbox(policy=policy, srt_path=srt_path or pinned_srt)
