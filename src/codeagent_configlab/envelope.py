"""Execution envelope and Candidate-2 security policy, as reusable configuration.

This translates the *already-tested* Candidate-2 controls
(``docs/CREDENTIAL_ISOLATION_CANDIDATE2.md``) into inspectable objects. It does not redesign
them. If a change here would materially alter Candidate 2, that is a regression to report, not
to make silently.

Two layers:

* :class:`SecurityPolicy` — the credential-isolation controls that are a **common environment
  control** across C0/C1/C2 (protocol §13/A1). Config-independent; hashable.
* :class:`ExecutionEnvelope` — the per-phase CLI/sandbox policy. The *implementation* envelope
  is identical for C0, C1 and C2 phase 2 (the CLAUDE.md treatment is a fixture-file concern,
  not a CLI flag), which the equality invariant test asserts. The *planning* envelope differs
  only in its tool set and read-only outer view (the C2 treatment).

Rendering that needs per-run paths (working copy, TMPDIR) is done by explicit ``render_*``
methods; the policy/envelope *identity* deliberately excludes those paths so it is stable
across runs and its hash is meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .hashing import canonical_json_hash

# Auth-override variable names removed before every claude invocation. MUST mirror
# setup/common.sh CCLAB_AUTH_OVERRIDE_VARS (a test asserts they match).
AUTH_OVERRIDE_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_REFRESH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)

# Tool sets (protocol §8 / readiness spike). Planning is read-only inspection only.
IMPLEMENTATION_TOOLS: tuple[str, ...] = ("Bash", "Read", "Edit", "Write", "Glob", "Grep")
PLANNING_TOOLS: tuple[str, ...] = ("Bash", "Read", "Glob", "Grep")

# The real production credential path. Referenced ONLY as a protected pathname; never read,
# copied, or opened by the harness. The fake-fixture path used in spikes/tests is NOT here.
DEFAULT_CREDENTIAL_PATH = "/home/cclab/.claude/.credentials.json"

# Narrow Claude-state write set inside the outer sandbox (readiness spike "narrow" set):
# session/runtime subpaths only, so user-level instruction/settings paths stay read-only.
CLAUDE_STATE_WRITE_SUBPATHS: tuple[str, ...] = (
    ".claude/projects",
    ".claude/session-env",
    ".claude/sessions",
    ".claude/shell-snapshots",
    ".claude/backups",
    ".claude/cache",
    ".claude/.credentials.json",
)

# G11 instruction loader (Claude Code 2.1.263). ``--setting-sources ""`` keeps project/local
# *settings* inactive but also disables the cwd memory walk, so the repository CLAUDE.md is never
# loaded. The additional-directory memory path is not gated by projectSettings: with this env var
# set, every ``--add-dir`` directory's CLAUDE.md, .claude/CLAUDE.md and .claude/rules/** are
# loaded as "Project" memory. The loader is identical for every configuration and phase; the
# treatment variable stays the presence/bytes of the root CLAUDE.md (docs/G11_TREATMENT_LOAD_SMOKE.md).
INSTRUCTION_LOADER = "add_dir_claude_md"
INSTRUCTION_LOADER_ENV = {"CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "1"}

# The five Anthropic auth/API hosts the outer sandbox allows (readiness spike).
ALLOWED_DOMAINS: tuple[str, ...] = (
    "api.anthropic.com",
    "claude.ai",
    "console.anthropic.com",
    "platform.claude.com",
    "statsig.anthropic.com",
)


@dataclass(frozen=True)
class SecurityPolicy:
    """Candidate-2 credential-isolation controls (config-independent, hashable).

    Fields correspond one-to-one to what Candidate 2 tested. The defaults ARE the accepted
    V0 controls; changing a default is a change to the security posture.
    """

    credential_path: str = DEFAULT_CREDENTIAL_PATH
    # outer sandbox
    outer_allow_all_unix_sockets: bool = True     # the single Candidate-2 outer delta
    deny_read_roots: tuple[str, ...] = ("/mnt/c",)  # + harness root, added at render time
    allowed_domains: tuple[str, ...] = ALLOWED_DOMAINS
    claude_state_write_subpaths: tuple[str, ...] = CLAUDE_STATE_WRITE_SUBPATHS
    # inner Claude Bash sandbox
    inner_sandbox_enabled: bool = True
    fail_if_unavailable: bool = True
    allow_unsandboxed_commands: bool = False
    auto_allow_bash_if_sandboxed: bool = False
    # built-in file tools (2.1.263: Write(path) rules are inert — Read()+Edit() only)
    permission_deny_tools: tuple[str, ...] = ("Read", "Edit")
    permission_deny_globs: tuple[str, ...] = ("**/.credentials.json",)
    # Working-copy subpaths that are active CLI input under the G11 loader (``--add-dir <wc>``
    # reads <wc>/.claude/settings*.json for plugin enablement/marketplaces, <wc>/.claude/agents,
    # skills, rules, CLAUDE.md). Write-protected in every phase: outer srt denyWrite (all tool
    # surfaces) + inner sandbox denyWrite (Bash) + Edit() deny rule (built-in tools).
    protected_wc_subpaths: tuple[str, ...] = (".claude",)
    # operating requirements
    seed_wc_settings: bool = True                 # every WC needs empty .claude/settings*.json
    sanitized_env_vars: tuple[str, ...] = AUTH_OVERRIDE_VARS
    disable_autoupdater: bool = True
    disable_nonessential_traffic: bool = True

    def identity_dict(self) -> dict:
        """Config-independent identity (no per-run paths) for hashing/recording."""
        return {
            "credential_path": self.credential_path,
            "outer_allow_all_unix_sockets": self.outer_allow_all_unix_sockets,
            "deny_read_roots": list(self.deny_read_roots),
            "allowed_domains": list(self.allowed_domains),
            "claude_state_write_subpaths": list(self.claude_state_write_subpaths),
            "inner_sandbox_enabled": self.inner_sandbox_enabled,
            "fail_if_unavailable": self.fail_if_unavailable,
            "allow_unsandboxed_commands": self.allow_unsandboxed_commands,
            "auto_allow_bash_if_sandboxed": self.auto_allow_bash_if_sandboxed,
            "permission_deny_tools": list(self.permission_deny_tools),
            "permission_deny_globs": list(self.permission_deny_globs),
            "protected_wc_subpaths": list(self.protected_wc_subpaths),
            "seed_wc_settings": self.seed_wc_settings,
            "sanitized_env_vars": list(self.sanitized_env_vars),
            "disable_autoupdater": self.disable_autoupdater,
            "disable_nonessential_traffic": self.disable_nonessential_traffic,
        }

    def policy_hash(self) -> str:
        return canonical_json_hash(self.identity_dict())

    # ---------------------------------------------------------------- rendering --
    def render_inner_settings(self, home: str, working_copy: str, run_tmp: str) -> dict:
        """The inline ``--settings`` PROTECT object for one run (Candidate-2 shape).

        ``sandbox.filesystem.allowWrite`` MUST include the working copy and TMPDIR, or Claude's
        Bash-tool bwrap cannot stage its settings mount and every Bash command fails (Candidate
        2 finding). Built-in denies use Read()+Edit() only (Write() rules are inert in 2.1.263).
        """
        cred = self.credential_path
        deny_rules: list[str] = []
        for tool in self.permission_deny_tools:
            deny_rules.append(f"{tool}(/{cred})")  # "//abs" == absolute-path rule
        for glob in self.permission_deny_globs:
            for tool in self.permission_deny_tools:
                deny_rules.append(f"{tool}({glob})")
        protected = self.protected_paths(working_copy)
        for path in protected:
            deny_rules.append(f"Edit(/{path}/**)")
        filesystem = {"denyRead": [cred], "allowWrite": [working_copy, run_tmp]}
        if protected:
            filesystem["denyWrite"] = list(protected)
        return {
            "sandbox": {
                "enabled": self.inner_sandbox_enabled,
                "failIfUnavailable": self.fail_if_unavailable,
                "allowUnsandboxedCommands": self.allow_unsandboxed_commands,
                "autoAllowBashIfSandboxed": self.auto_allow_bash_if_sandboxed,
                "credentials": {"files": [{"path": cred, "mode": "deny"}]},
                "filesystem": filesystem,
            },
            "permissions": {"deny": deny_rules},
        }

    def protected_paths(self, working_copy: str) -> list[str]:
        return [f"{working_copy.rstrip('/')}/{sub}" for sub in self.protected_wc_subpaths]

    def render_outer_srt(
        self, mode: str, home: str, harness_root: str, working_copy: str, run_tmp: str
    ) -> dict:
        """The outer srt config for one run. ``mode`` is ``"impl"`` or ``"ro"`` (C2 phase 1)."""
        if mode not in ("impl", "ro"):
            raise ValueError(f"srt mode must be 'impl' or 'ro', got {mode!r}")
        state_writes = [f"{home}/{p}" for p in self.claude_state_write_subpaths]
        state_writes.append(f"{home}/.claude.json")
        deny_read = list(self.deny_read_roots) + [harness_root]
        net = {
            "allowedDomains": list(self.allowed_domains),
            "deniedDomains": [],
        }
        if self.outer_allow_all_unix_sockets:
            net["allowAllUnixSockets"] = True
        if mode == "ro":
            allow_write = state_writes + [run_tmp]
            deny_write = [working_copy]
        else:
            allow_write = [working_copy] + state_writes + [run_tmp]
            deny_write = self.protected_paths(working_copy)
        return {
            "network": net,
            "filesystem": {
                "denyRead": deny_read,
                "allowRead": [working_copy, run_tmp],
                "allowWrite": allow_write,
                "denyWrite": deny_write,
            },
        }


@dataclass(frozen=True)
class ExecutionEnvelope:
    """Per-phase CLI + sandbox policy (identity excludes per-run paths).

    Equality is by field value (frozen dataclass), which is exactly what the C0/C1/C2
    implementation-envelope invariant relies on.
    """

    phase: str                              # "implementation" | "planning"
    tools: tuple[str, ...]
    srt_mode: str                           # "impl" | "ro"
    security_policy: SecurityPolicy
    permission_mode: str = "bypassPermissions"
    strict_mcp_config: bool = True
    setting_sources: str = ""              # --setting-sources "" (no user/project/local)
    system_prompt_snapshot: str = "off"
    output_format: str = "stream-json"
    verbose: bool = True
    instruction_loader: str = INSTRUCTION_LOADER   # G11: identical for every config and phase

    def identity_dict(self) -> dict:
        return {
            "phase": self.phase,
            "tools": list(self.tools),
            "srt_mode": self.srt_mode,
            "permission_mode": self.permission_mode,
            "strict_mcp_config": self.strict_mcp_config,
            "setting_sources": self.setting_sources,
            "system_prompt_snapshot": self.system_prompt_snapshot,
            "output_format": self.output_format,
            "verbose": self.verbose,
            "instruction_loader": self.instruction_loader,
            "security_policy": self.security_policy.identity_dict(),
        }

    def envelope_hash(self) -> str:
        return canonical_json_hash(self.identity_dict())

    # ---------------------------------------------------------------- argv build --
    def loader_env(self) -> dict:
        """Environment the instruction loader needs (same for every configuration)."""
        return dict(INSTRUCTION_LOADER_ENV) if self.instruction_loader == INSTRUCTION_LOADER else {}

    def build_claude_flags(
        self, *, model: str, effort: str, session_flag: tuple[str, str], protect_json: str,
        add_dir: Optional[str] = None,
    ) -> list[str]:
        """Build the ``claude -p`` flag list for this envelope.

        ``session_flag`` is ``("--session-id", uuid)`` for a new session or
        ``("--resume", uuid)`` to continue one. ``protect_json`` is the inline ``--settings``
        JSON string produced from :meth:`SecurityPolicy.render_inner_settings`. ``add_dir`` is
        the working copy; the G11 loader requires it (``--add-dir <wc>``). ``effort`` is sent
        explicitly via ``--effort`` so it is never inherited from a session/settings default.
        """
        flags = ["-p", session_flag[0], session_flag[1], "--tools", ",".join(self.tools),
                 "--model", model, "--effort", effort, "--permission-mode", self.permission_mode]
        if self.strict_mcp_config:
            flags.append("--strict-mcp-config")
        flags += ["--settings", protect_json, "--setting-sources", self.setting_sources]
        flags += ["--system-prompt-snapshot", self.system_prompt_snapshot,
                  "--output-format", self.output_format]
        if self.verbose:
            flags.append("--verbose")
        if self.instruction_loader == INSTRUCTION_LOADER:
            if not add_dir:
                raise ValueError("the add_dir_claude_md instruction loader needs the working copy")
            flags += ["--add-dir", add_dir]
        elif self.instruction_loader != "none":
            raise ValueError(f"unknown instruction loader {self.instruction_loader!r}")
        return flags


def implementation_envelope(
    configuration: str, security_policy: Optional[SecurityPolicy] = None
) -> ExecutionEnvelope:
    """The implementation envelope for C0, C1 or C2 phase 2.

    It is intentionally **independent of** ``configuration``: the only treatment difference
    (the CLAUDE.md) is a working-copy fixture file, not a CLI flag, so C0/C1/C2 must build the
    same implementation envelope. The parameter is accepted (and validated) so callers pass the
    config explicitly, but it does not branch the result — the equality invariant test guards
    against anyone accidentally making it config-dependent.
    """
    if configuration not in ("C0", "C1", "C2"):
        raise ValueError(f"configuration must be C0/C1/C2, got {configuration!r}")
    return ExecutionEnvelope(
        phase="implementation",
        tools=IMPLEMENTATION_TOOLS,
        srt_mode="impl",
        security_policy=security_policy or SecurityPolicy(),
    )


def planning_envelope(security_policy: Optional[SecurityPolicy] = None) -> ExecutionEnvelope:
    """The C2 phase-1 planning envelope: restricted tools + read-only outer view.

    Differs from the implementation envelope ONLY in ``tools`` (no Edit/Write) and
    ``srt_mode="ro"`` (working copy read-only) — the read-only planning treatment. The
    credential-isolation :class:`SecurityPolicy` is identical to implementation.
    """
    return ExecutionEnvelope(
        phase="planning",
        tools=PLANNING_TOOLS,
        srt_mode="ro",
        security_policy=security_policy or SecurityPolicy(),
    )
