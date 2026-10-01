"""Shared test helpers: build valid manifests for each configuration."""

from __future__ import annotations

from codeagent_configlab.envelope import (
    IMPLEMENTATION_TOOLS,
    PLANNING_TOOLS,
    SecurityPolicy,
    implementation_envelope,
)
from codeagent_configlab.ids import new_run_id, new_workspace_token
from codeagent_configlab.manifest import RunManifest

_POLICY = SecurityPolicy()
_POLICY_HASH = _POLICY.policy_hash()
_SETTINGS_HASH = implementation_envelope("C0").envelope_hash()


def make_manifest(configuration: str = "C0", **overrides) -> RunManifest:
    """Build a schema-valid manifest for the given configuration with sensible test defaults."""
    base = dict(
        run_id=new_run_id(),
        task_id="P-smoke-001",
        task_version_hash="deadbeef",
        language="python",
        task_category="feature",
        configuration=configuration,
        repetition=1,
        workspace_token=new_workspace_token(),
        settings_policy_hash=_SETTINGS_HASH,
        security_policy_hash=_POLICY_HASH,
        task_statement_hash="cafef00d",
        implementation_tool_set=IMPLEMENTATION_TOOLS,
    )
    if configuration in ("C1", "C2"):
        base["claude_md_hash"] = "0" * 64
    if configuration == "C2":
        base["planning_tool_set"] = PLANNING_TOOLS
        base["planning_wrapper_hash"] = "1" * 64
        base["approval_message_hash"] = "2" * 64
    base.update(overrides)
    return RunManifest(**base)


# --- harmless test treatment (NOT benchmark content): identical bytes for C1 and C2 ----------
from codeagent_configlab.hashing import sha256_text  # noqa: E402
from codeagent_configlab.treatment import TASK_STATEMENT_SLOT, Treatment  # noqa: E402

TEST_STATEMENT = "Add a function multiply(a, b) to calc.py that returns a * b."
TEST_CLAUDE_MD = b"# test-only treatment fixture\nThis file exists only to exercise the harness.\n"
TEST_WRAPPER = "TEST-ONLY PLANNING WRAPPER\n" + TASK_STATEMENT_SLOT + "\nEND TEST WRAPPER\n"
TEST_APPROVAL = "TEST-ONLY FIXED APPROVAL MESSAGE\n"


def make_treatment(configuration: str):
    """The test treatment for a configuration (None for C0)."""
    if configuration == "C0":
        return None
    if configuration == "C1":
        return Treatment(claude_md=TEST_CLAUDE_MD)
    return Treatment(claude_md=TEST_CLAUDE_MD, planning_wrapper=TEST_WRAPPER,
                     approval_message=TEST_APPROVAL)


def make_treated_manifest(configuration: str = "C0", **overrides) -> RunManifest:
    """A manifest whose treatment/statement hashes match :func:`make_treatment` + TEST_STATEMENT."""
    t = make_treatment(configuration)
    fields = {"task_statement_hash": sha256_text(TEST_STATEMENT)}
    if t is not None:
        fields["claude_md_hash"] = t.claude_md_hash
    if configuration == "C2":
        fields["planning_wrapper_hash"] = t.planning_wrapper_hash
        fields["approval_message_hash"] = t.approval_message_hash
    fields.update(overrides)
    return make_manifest(configuration, **fields)


# --- evaluator sandbox test double (G5s) ------------------------------------------------------
import shutil as _shutil  # noqa: E402
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402


class FakeSandbox:
    """Identity command wrapper for the offline (Windows) evaluator suite. NOT a sandbox.

    Its ``record()`` says ``production_safe: False``; the real evaluator sandbox is
    ``evaluator_sandbox.SrtEvaluatorSandbox`` and is exercised in ``test_evaluator_sandbox.py``.
    Hooks let tests simulate initialization/preflight failures and count invocations.
    """

    production_safe = False

    def __init__(self, fail_prepare=None, fail_preflight=False, fail_postflight=False,
                 launcher_fails_for=(), forge_trailer_for=()):
        self.fail_prepare = fail_prepare
        self.fail_preflight = fail_preflight
        self.fail_postflight = fail_postflight
        # G8 simulations: the launcher dies before running the check (srt failure), or the
        # attested status disagrees with the process exit code.
        self.launcher_fails_for = set(launcher_fails_for)
        self.forge_trailer_for = set(forge_trailer_for)
        self.check_runs = 0
        self.flights = 0
        self.wrapped: list[list[str]] = []

    def prepare(self, root, work, home):
        if self.fail_prepare:
            raise RuntimeError(self.fail_prepare)

    def wrap(self, argv, cwd):
        self.wrapped.append(list(argv))
        return list(argv)

    def wrap_check(self, argv, cwd, nonce):
        self.check_runs += 1
        joined = " ".join(argv)
        if any(k in joined for k in self.launcher_fails_for):
            return [_sys.executable, "-c",
                    "import sys; sys.stderr.write('Error: simulated sandbox failure'); sys.exit(1)"]
        forge = any(k in joined for k in self.forge_trailer_for)
        code = "\n".join([
            "import subprocess, sys",
            "n, forge = sys.argv[1], sys.argv[2] == '1'",
            "rc = subprocess.run(sys.argv[3:]).returncode",
            "sys.stdout.write('\\nCCLAB-EVAL-RC:%s:%s\\n' % (n, 0 if forge else rc))",
            "sys.stdout.flush()",
            "sys.exit(rc)",
        ])
        return self.wrap([_sys.executable, "-c", code, nonce, "1" if forge else "0", *argv], cwd)

    def env(self):
        return {}

    def resolve_program(self, argv0, work):
        if "/" in argv0 or "\\" in argv0:
            p = _Path(argv0)
            return str(p if p.is_absolute() else _Path(work) / argv0)
        found = _shutil.which(argv0)
        if found is None:
            raise FileNotFoundError(f"check program {argv0!r} not found")
        return found

    def preflight_argv(self, programs, nonce):
        self.flights += 1
        fail = self.fail_preflight if self.flights == 1 else self.fail_postflight
        code = ("import os, sys\n"
                "missing = [p for p in sys.argv[2:] if not os.path.exists(p)]\n"
                "if missing or sys.argv[1] == 'FAIL': print('missing', missing); sys.exit(3)\n"
                f"print({nonce!r})\n")
        return [_sys.executable, "-c", code, "FAIL" if fail else "OK", *programs]

    def record(self):
        return {"kind": "test-fake", "production_safe": False}
