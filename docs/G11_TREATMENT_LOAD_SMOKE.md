# G11 — Repository CLAUDE.md treatment loading (Claude Code 2.1.263)

**Update 2026-09-28: RESOLVED.** After operator re-login, the real `G11_TREATMENT_LOAD_SMOKE_ONLY` rerun passed (`G11_SMOKE: PASS`, marker loaded, exit 0, immutability and AF_UNIX checks held, no residue). That run was recorded as `agent_outcome=auth_failure` despite succeeding, which exposed the G4 classifier false positive, now fixed (`docs/G4_OUTCOME_CLASSIFIER.md`). The text below is the 2026-09-27 record.

Status: **BLOCKED on infrastructure (expired OAuth token), 2026-09-27.** The loader mechanism is
chosen, implemented and verified model-free. Positive loading of the repository `CLAUDE.md` is
**not yet proven**: the one approved real smoke call reached a real session but got
`401 OAuth access token has expired`. This is an infrastructure outcome, not a mechanism failure.
Namespace: `G11_TREATMENT_LOAD_SMOKE_ONLY`. It is never pilot or final data.

## 1. Installed-version loader behaviour (static analysis of the 2.1.263 binary)

`--setting-sources ""` parses to `[]` (`par("") → []`), so the enabled sources are only
`flagSettings` and `policySettings`. The memory loader then behaves as follows:

- **cwd ancestor walk**: root `CLAUDE.md`, `.claude/CLAUDE.md` and `.claude/rules/**` load only if
  `hF("projectSettings")`. `CLAUDE.local.md` loads only if `hF("localSettings")`. Lazy nested
  subdirectory memory is gated by `projectSettings` as well.
- **additional directories**: if `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` is set, then for
  every `--add-dir` directory the loader reads `CLAUDE.md`, `.claude/CLAUDE.md` and
  `.claude/rules/**` as `"Project"` memory **without** the `projectSettings` gate.
  `CLAUDE.local.md` stays gated by `localSettings`. `--add-dir` values are stored unfiltered, so
  the cwd itself can be added.
- **workspace restriction**: `hF` also has a `sparesInstructionFiles` path. Nothing in 2.1.263
  sets it (there are no callers and no flag), so it is not reachable.
- **side effects of `--add-dir <dir>`**: the CLI reads `enabledPlugins` and
  `extraKnownMarketplaces` from `dir/.claude/settings.json` and `dir/.claude/settings.local.json`
  (ungated). It discovers `dir/.claude/agents` and `dir/.claude/skills`, and treats `dir` as a
  working directory (here that is the cwd, so no new access).
- **project settings** (hooks, env, permissions, `sandbox.*`) remain inactive. The code logs
  "ignoring permission rules and sandbox.filesystem entries from disabled setting source".

| Mechanism | Root CLAUDE.md | Project settings | Local settings | Suitable |
|---|---|---|---|---|
| `--setting-sources ""` (pre-G11) | no | no | no | no — treatment never delivered |
| `--setting-sources project` | yes | **yes** (hooks outside inner sandbox, env, permissions, sandbox merge) | no | no — agent-writable active config |
| `--setting-sources project,local` | yes (+local.md) | yes | yes | no |
| workspace restriction (`sparesInstructionFiles`) | yes | no | no | not reachable in 2.1.263 |
| **`--add-dir <wc>` + `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`, sources `""`** | **yes** (+`.claude/CLAUDE.md`, `.claude/rules`) | no (only plugin enablement/marketplaces, agents, skills from `<wc>/.claude`) | no | **chosen**, with `<wc>/.claude` immutable |
| `--system-prompt(-file)` / prompt concatenation | n/a | — | — | rejected: a different treatment mechanism (not repository CLAUDE.md) |

## 2. Chosen mechanism and invariants

- **One loader for every invocation**: C0, C1, C2 phase 1 and C2 phase 2 all run with
  `--setting-sources ""`, `--add-dir <wc>` and `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`.
  This is `ExecutionEnvelope.instruction_loader = "add_dir_claude_md"`, which is part of the
  envelope hash. The treatment variable remains only the presence and bytes of the root
  `CLAUDE.md`.
- **Caveat**: in this mode, nested subdirectory `CLAUDE.md` and `CLAUDE.local.md` are not loaded.
  Neither is part of the treatment, and both remain fail-closed by the instruction-state
  invariant.
- **`<wc>/.claude` is immutable in every phase.** This is a common Candidate-2 control
  (`SecurityPolicy.protected_wc_subpaths`), enforced three ways:
  - outer srt `denyWrite: [<wc>/.claude]`, which covers every tool surface because the whole CLI
    runs inside it;
  - inner sandbox `filesystem.denyWrite: [<wc>/.claude]`;
  - permission deny rule `Edit(/<wc>/.claude/**)`.
- **Extended runtime seeding**: `.claude/commands/` and `.claude/agents/` now exist as empty
  directories. sandbox-runtime always write-protects them and needs a mount target that it can no
  longer create under a read-only `.claude`.
- **Effective sources** are listed in `treatment.EFFECTIVE_INSTRUCTION_SOURCES`. The invariant
  already covers all of them (every `CLAUDE.md`/`CLAUDE.local.md`, everything under `.claude/`).

## 3. Model-free evidence

- **Immutability probe** (`spike/g11-treatment-load/settings_immutability_probe.py`), run as
  `cclab` with the real outer srt `impl` config:
  - fail with EROFS or EBUSY: shell redirect, overwriting `settings.local.json`, Python write,
    Node `fs` write (the same path the CLI's Write/Edit tools use), creating `agents/`, `rules/`
    or `.claude/CLAUDE.md`, writing into the seeded `commands/`, deleting `settings.json`,
    renaming `.claude`, deleting `.claude`;
  - a normal working-copy write succeeds;
  - both settings files are unchanged afterwards.
- **Startup diagnosis** (`spike/g11-treatment-load/startup_diagnosis.py`): the real
  `srt -- claude -p` argv, run with a whitespace-only prompt (2.1.263 stops before any API request
  in that case). It covers pre-G11, loader-only, protect-only and the full G11 configuration.
  After the seeding fix, all four reach "Input contained only whitespace".
- **Tests**:
  - loader identical for C0, C1 and both C2 phases;
  - `--add-dir <WC>`, `--setting-sources ""` and the env var present in every real-runner
    invocation;
  - `.claude` protection rendered in the outer, inner and permission layers;
  - drift and preflight failure for `.claude/agents`, `skills`, `commands` and
    `settings.local.json`.

## 4. Real calls (2 CLI invocations, 1 model request attempted)

1. **Attempt 1.** The CLI exited 1 before any session. There was no `init` event and no project
   state. The cause was reproduced model-free: `bwrap: Can't create file at <wc>/.claude/commands:
   Read-only file system`. Fixed by the seeding above. The smoke script had also resolved
   `claude` via PATH to the **Windows** npm shim under `/mnt/c` for its `auth status` and cleanup
   calls. `_resolve_exe` now rejects `/mnt/` paths, and `RealCleanupRunner` resolves the WSL CLI.
2. **Attempt 2** (approved retry; session `ae1fd6a8-…`):
   - A real session started. `init` showed model `claude-haiku-4-5-20251001`,
     `bypassPermissions` and tools `[Bash, Edit, Glob, Grep, Read, Write]`; session continuity
     was OK.
   - The API answered `401 OAuth access token has expired`, and the harness classified this as
     `auth_failure`.
   - Evidence that still stands:
     - the envelope with the G11 loader and the protected `.claude` starts a real session;
     - the probe settings' `SessionStart` hook **did not run**, so project settings are
       inactive;
     - `.claude/settings*.json` were unchanged and `.claude` held only the seeds;
     - cleanup ran with exit 0 and left no residue;
     - `auth status` (WSL CLI) reports `claude.ai / firstParty / pro`.
   - The credential file's mtime is unchanged since 2026-09-25, so no refresh has been
     persisted since the WSL gate.

## 5. Not yet shown (why BLOCKED)

- Positive load: the marker answer is missing because the model never ran.
- Inner Bash sandbox behaviour with the protected `.claude`: the AF_UNIX probe and Bash/Write
  attempts never ran.
- Whether OAuth token refresh works from inside the outer sandbox. The outer sandbox allows
  writing only the credential **file**, not `~/.claude/` entries a refresh might need. This
  belongs to setup/auth and was not investigated or changed here.

**Next step (operator):** re-authenticate `cclab` interactively (`claude` login as cclab). Then run
`g11_smoke.py --real` once. If the token expires again during sandboxed use, the refresh-in-sandbox
question becomes a separate infrastructure gap.
