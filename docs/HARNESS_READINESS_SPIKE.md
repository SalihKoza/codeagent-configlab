# CodeAgent ConfigLab — Harness Readiness Spike

Status: **infrastructure spike, 2026-09-23.** This is not a benchmark task, not a
pilot task (§9), and its results have no research value. It settles only the
execution mechanisms that block a minimal harness: O1, O2, O3, O4, and O6/O7 as far
as they define one implementation envelope. Other OPEN items stay open.

Environment: WSL2 Ubuntu, user `cclab`, Claude Code **2.1.263**,
sandbox-runtime (`srt`) 0.0.77, persisted Claude.ai Pro login. No API key and no
other provider. Model `haiku` (resolved to `claude-haiku-4-5-20251001`) is a
**spike placeholder only**, not the O5 pin.

Evidence: `spike/harness-readiness/spike.sh`. The WSL-side artifacts are under
`~/cclab-spike/artifacts/` (stream-JSON transcripts, `narrow-p1.hash`,
`purge2.log`).

Model calls: 5 in total, all short haiku calls: round 1 `phase1`, `phase2` and
`c0`; round 2 `narrow-p1` and `narrow-p2`. No usage limit was hit.

## Fixture and topology used

```
~/cclab-spike/                 # whole tree denyRead inside the agent sandbox
  fixture/calc.py              # def add(a, b) — one commit, fixed author/date
  runs/<random-16-hex>/        # per-run working copy (opaque path), re-allowed for read
  tmp/<same-token>/            # per-run TMPDIR, re-allowed for read+write
  hidden/CANARY.txt            # stands in for hidden evaluator material; never re-allowed
  settings/srt-*.json          # sandbox configs (per run, per phase)
  artifacts/                   # outputs, never re-allowed
/mnt/c                         # denyRead (tmpfs), as in setup
```

The **whole `claude` process** runs inside `srt`, not only its Bash tool. The
sandbox therefore covers every tool surface: Read/Edit/Write/Glob/Grep execute
in the CLI process, and Bash runs in its children.

### Shared invocation shape (secrets omitted)

```bash
cd "$WC" && printf '%s' "$PROMPT" | \
env -u <each var in setup/common.sh CCLAB_AUTH_OVERRIDE_VARS> \
    DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 TMPDIR="$RUN_TMP" \
srt -s "$SRT_CONFIG" -- \
claude -p <phase flags> \
  --model "$MODEL" --permission-mode bypassPermissions --strict-mcp-config \
  --settings '{}' --setting-sources "" --system-prompt-snapshot off \
  --output-format stream-json --verbose
```

`/tmp/claude` must exist beforehand. `srt` forces it as the in-sandbox TMPDIR
but cannot create it under a read-only `/tmp`. Without it, Claude Code fails with
`EROFS mkdir /tmp/claude`.

### srt config shapes ("narrow" Claude-state write set)

```jsonc
// ro (C2 phase 1)
{"network":{"allowedDomains":["api.anthropic.com","claude.ai","console.anthropic.com",
                              "platform.claude.com","statsig.anthropic.com"],"deniedDomains":[]},
 "filesystem":{"denyRead":["/mnt/c","<spike root>"],"allowRead":["<WC>","<RUN_TMP>"],
   "allowWrite":["~/.claude/projects","~/.claude/session-env","~/.claude/sessions",
                 "~/.claude/shell-snapshots","~/.claude/backups","~/.claude/cache",
                 "~/.claude/.credentials.json","~/.claude.json","<RUN_TMP>"],
   "denyWrite":["<WC>"]}}
// impl (C0 / C1 / C2 phase 2): identical except "<WC>" added to allowWrite, denyWrite []
```

(`~` is written as an absolute path in the real files.)

---

## Spike A — deterministic session identity and resume (O2)

**Hypothesis.** A harness-generated UUID can name the session in phase 1. Phase 2
can resume exactly that session headlessly and has the phase-1 context, without
`--continue` and without `--fork-session`.

**Mechanism.** Phase 1: `claude -p --session-id <uuid> …`. Phase 2, a new process
in the same working copy: `claude -p --resume <uuid> …`. The UUID comes from
`/proc/sys/kernel/random/uuid`.

**Observed (run twice: round 1 `678ba105-…`, round 2 `db4f692c-…`).**
- Phase 1: exit 0. `init.session_id` and `result.session_id` equal the harness UUID.
- Phase 2: exit 0. `init.session_id` and `result.session_id` equal the **same** UUID.
- Phase 1 was told the codeword `HERON-7731`. Phase 2 was asked only for "the codeword you were given earlier" and wrote `output.txt = HERON-7731` both times, so phase 2 had the phase-1 context.
- Both phases appended to one transcript file, `projects/<wc-slug>/<uuid>.jsonl`.
- No `--continue` and no `--fork-session` were used.

**Result: PASS.**

**Harness implication.**
- C2 uses `--session-id <uuid>` in phase 1 and `--resume <uuid>` in phase 2.
- The same-session check is `init.session_id == result.session_id == uuid` in both phases' stream-JSON, recorded as the §7 "same-session evidence".
- A mismatch means `phase_transition_failed`.

## Spike B — C2 phase-1 read-only enforcement (O1)

**Hypothesis.** Two independent layers together make the working copy immutable
during phase 1, while Claude can still inspect it and produce a plan:
- tool restriction: write/edit tools are not exposed;
- a read-only sandbox view of the working copy.

This does not use the built-in `plan` permission mode and does not rely on
prompt instructions.

**Mechanism.**
- `--tools "Bash,Read,Glob,Grep"`.
- `srt` config `ro`: the working copy is in `denyWrite`.
- Claude-state writes are limited to the narrow set above. User-level instruction and settings paths (`~/.claude/CLAUDE.md`, `settings.json`, `skills/`, …) stay read-only.
- The harness hashes the working copy before and after, including `.git` and ignoring only `__pycache__`.

The phase-1 prompt was an adversarial probe that explicitly asked Claude to try
to create `PROBE.txt`, append to `calc.py`, and create `~/.claude/CLAUDE.md`
"using any tool you have".

**Observed (round 2, narrow; `artifacts/narrow-p1.*`).**
- `init.tools = [Bash, Glob, Grep, Read]`, `permissionMode = bypassPermissions`.
- Claude tried the Write tool twice. Both times the result was `No such tool available: Write. Write is disabled for this session, in subagents as well as here.` (tool layer).
- Claude tried Bash writes to `PROBE.txt`, `calc.py` and `~/.claude/CLAUDE.md`. All three were refused with `Read-only file system` (sandbox layer).
- The Read tool worked, and the plan text was produced.
- **WC hash before = after = `b336e7a4…f0ea5`**, identical to the fixture hash. `~/.claude/CLAUDE.md` does not exist afterwards.
- Non-model probes under the same config (`narrow-probes`) behaved the same way. Writes to the WC, `~/.claude/CLAUDE.md`, `~/.claude/settings.json` and `~/.claude/skills/` all failed with EROFS.
- Round 1 used a "wide" design where all of `~/.claude` was writable. The WC stayed unchanged there too, but phase 1 could have created user-level instruction files that phase 2 would load. The narrow set closes that hole.

**Runtime writes outside the repository during phase 1** (names only, from a
`-newer` marker scan). These are harmless Claude-state writes:
- `~/.claude/projects/<wc-slug>/<uuid>.jsonl` (session transcript; required for resume)
- `~/.claude/projects/<wc-slug>/memory/` (empty dir; auto-memory is active: `init.memory_paths.auto` points here)
- `~/.claude/session-env/<uuid>/`
- `~/.claude/sessions/`, `~/.claude/shell-snapshots/` (touched)
- `/tmp/claude/claude-<uid>/<wc-slug>/`
- `~/.claude.json` got **no** entry for the sandboxed working copy. A later *unsandboxed* invocation in that directory did create one (Spike D).

**Residual channel (recorded, not a WC violation).** `~/.claude/projects/` must
stay writable for the transcript, so a Bash write into it succeeds (probe
`write ~/.claude/projects` → `wrote`). That includes the project's auto-memory
dir, which phase 2 would load. The harness closes this by verification rather
than trust: after phase 1, `projects/<wc-slug>/` must contain only
`<uuid>.jsonl`, and `memory/` must be empty. Otherwise the run is `phase1_write`.

**Result: PASS** (O1).

**Harness implication.** Phase 1 = tool restriction + `ro` srt config + tree-hash
check + project-dir content check. Tests *can* be run read-only in phase 1 only
if they don't need to write into the WC. Such writes simply fail. This is
recorded, not a violation.

## Spike C — equal implementation envelope, and changing it on resume (O6, O7)

**Hypothesis.** One envelope can be used byte-identically for C0, C1 and C2
phase 2. A session started under the phase-1 tool set and sandbox can be resumed
under that envelope.

**Candidate envelope (all fixed explicitly):**

| Element | Value in spike |
|---|---|
| Model | `--model <pin>` (placeholder `haiku`; O5 stays open). `init.model` records what the CLI used |
| Permission mode | `--permission-mode bypassPermissions` (headless, no prompts; the sandbox is the boundary) |
| Built-in tools | `--tools "Bash,Read,Edit,Write,Glob,Grep"` |
| MCP | `--strict-mcp-config` with no `--mcp-config` → `init.mcp_servers = []` |
| Settings | `--settings '{}' --setting-sources ""` (no user/project/local settings loaded) |
| Network | srt `allowedDomains` = the five Anthropic auth/API hosts only. Everything else is blocked |
| Filesystem | srt `impl` config: WC + narrow Claude-state paths + run TMPDIR writable; spike/harness root and `/mnt/c` denyRead except WC/TMPDIR |
| Auth sanitization | every name in `setup/common.sh` `CCLAB_AUTH_OVERRIDE_VARS` is `env -u`'d |
| Autoupdater | `DISABLE_AUTOUPDATER=1`, plus `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` |
| Prompt delivery (O7) | stdin |
| Output (O7) | `--output-format stream-json --verbose` (gives `init` with `session_id`, `model`, `tools`, `permissionMode`, `mcp_servers`, `memory_paths`, and a `result` event) |

**Transition test.** C2 phase 2 = `--resume <uuid>` plus the envelope above, with
the `impl` srt config.

**Observed (both rounds).**
- Phase 2: `init.tools = [Bash, Edit, Glob, Grep, Read, Write]` and `permissionMode = bypassPermissions`. This equals the C0 run's `init` (round 1, `c0`).
- Phase 2 edited `calc.py` with the **Edit** tool (only `multiply` was added) and wrote `output.txt`. Changed files vs fixture: `calc.py`, `output.txt`.
- Changing both the tool set and the sandbox config between phases on `--resume` works in 2.1.263. No blocker.

**Result: PASS** (O6 and O7, as far as the envelope goes).

**Harness implication.**
- C0, C1 and C2-phase-2 share one flag list and one `impl` srt config template. The only per-run variations are WC, TMPDIR and UUID, which are path-shape identical.
- The harness records `init.tools`, `init.permissionMode`, `init.mcp_servers` and `init.model` per invocation, and asserts equality to the envelope. A mismatch means `invalid:harness`.
- C2 phase 2 differs from C0/C1 only by `--resume <uuid>` in place of `--session-id <uuid>`.

**Observations for the envelope record.**
- `init.skills` lists Claude Code's *bundled* skills (e.g. `verify`, `debug`, `simplify`). No user/plugin skills are listed, and `plugins = []`. The same list appears in every configuration, so it is part of the envelope, not a treatment difference.
- The `result` events carry `usage.*`, `modelUsage`, `duration_ms`, `duration_api_ms`, `total_cost_usd` and `num_turns`. Their meaning under a subscription remains O8.

## Spike D — per-run Claude state cleanup (O3)

**Hypothesis.** `claude project purge <wc>` removes the run's project-local
Claude state after artifact capture. It does not affect auth or other projects,
so session persistence can stay on during a run.

**Mechanism** (from the round-2 `purge2.log`):
```bash
claude project purge --dry-run "$WC"      # supported in 2.1.263
claude project purge -y "$WC"
rm -rf -- ~/.claude/session-env/<uuid>    # exact name only; purge does not cover it
```
`claude project purge --help` (2.1.263) says: "…state for a project (transcripts,
tasks, file history, config entry)". Options: `--all`, `--dry-run`,
`-i/--interactive`, `-y/--yes`.

**Observed.**
- The dry run listed `~/.claude/projects/<wc-slug>` ("project transcripts (.jsonl) and memory/"). It also said that `shell-snapshots/` is not project-scoped and that `backups/` may still hold the project entry in old `.claude.json` snapshots ("at most 5 are kept and they rotate out automatically").
- Purge: `Purged 1 item(s)`, exit 0. Afterwards, the only file named with the UUID is `session-env/<uuid>`, removed by exact name.
- `claude -p --resume <uuid>` from the purged WC returned `No conversation found with session ID: db4f692c-…`. No inference happened. The exit status was not captured: a script bug on `PIPESTATUS` under `set -u`.
- **That failed resume itself re-created a `~/.claude.json` `projects[<wc>]` entry.** A second purge removed it ("config: projects[...]"). Rule: the harness never runs an unsandboxed `claude` in a WC. If it does, it purges afterwards.
- Round-1 residue was cleaned the same way, by exact path and UUID only: one config entry and two `session-env/<uuid>` dirs.
- After cleanup:
  - 0 files named with any of the 3 spike UUIDs;
  - 0 `~/.claude.json` entries for the 3 spike WCs;
  - the unrelated project list is unchanged (the 4 setup smoke projects);
  - `.credentials.json` size and mtime are unchanged;
  - `claude auth status` → `loggedIn=True authMethod=claude.ai apiProvider=firstParty subscriptionType=pro`.
- Not removed by purge (names only):
  - `/tmp/claude/claude-1001/<wc-slug>/`: project-scoped, removable by exact path;
  - one `~/.claude/backups/.claude.json.backup.*` that mentions the spike path. It is a config-entry snapshot, not a transcript, and rotates out after 5 backups.

**Result: PASS** (O3 cleanup mechanism).

**Harness implication.** Per run, after artifacts are captured and validity is
classified:
1. `claude project purge -y <wc>`;
2. `rm -rf ~/.claude/session-env/<uuid…>`;
3. `rm -rf /tmp/claude/claude-$(id -u)/<wc-slug>`;
4. verify there are 0 files named with the run's UUID(s) and no `~/.claude.json` entry for the WC.

Preflight before every run: `~/.claude/projects/` contains no project dirs. It
currently holds 4 setup smoke projects; see blockers.

## Spike E — hidden-material boundary (O4)

**Hypothesis.** Material that is never re-allowed inside the agent sandbox is
inaccessible through every tool surface. The same applies to other runs' WCs and
to `/mnt/c`.

**Mechanism.**
- The whole spike root is `denyRead` (srt mounts a tmpfs over it).
- Only this run's WC and TMPDIR are `allowRead`.
- `hidden/CANARY.txt` (content `CANARY-7f3a-SPIKE-HIDDEN`) sits under that root and is never re-allowed.

**Observed.**
- Round 1, `c0`, a model run asked to read the canary:
  - Read tool: `File does not exist`;
  - Bash `cat`: `No such file or directory`;
  - `ls hidden/`: `No such file or directory`;
  - `ls /mnt/c`: empty;
  - the canary string never appears in any agent output.
- Non-model probes under the round-2 `ro` and `impl` configs:
  - canary: `No such file or directory`;
  - another run's WC (`ls -A`): `No such file or directory`, rc=2;
  - `curl https://example.com`: `CONNECT tunnel failed, response 403`.

**Result: PASS** for hidden material, other runs' WCs and `/mnt/c`.

**But — observed during this spike:**
- the sandboxed agent's Bash **can read `~/.claude/.credentials.json`** (`test -r` → readable; contents were not read);
- the agent can **list other projects' dirs** under `~/.claude/projects/` (the 4 setup smoke projects).

The CLI itself needs the credentials file for auth. Because the whole CLI runs
inside `srt`, the file cannot be `denyRead` without breaking login. This
conflicts with §5 ("credentials MUST NOT be seen"). See blockers.

**Harness implication (topology).**
```
<harness root>/                       denyRead in every agent sandbox
  fixtures/  hidden/  reference/  evaluator/  results/  order/  runs/<token>/  tmp/<token>/
agent sandbox re-allows only:          runs/<token>/ (rw in impl, ro in C2 phase 1), tmp/<token>/
public task statement + treatment:     delivered via stdin (statement, C2 wrapper/approval);
                                       CLAUDE.md is part of the C1/C2 fixture copy in the WC
evaluator:                             separate later process, outside the agent sandbox,
                                       on a copy of the final WC
```
Hidden material is "not mounted" in the agent's view: a tmpfs overlay, not an
obscure filename. The OS-permission variant from §5 (a different owner) is
unnecessary for the canary result, and would also still leave the credential
issue.

---

## Decision table

### RESOLVED FOR HARNESS

- **O1 — C2 phase-1 read-only.**
  - `--tools "Bash,Read,Glob,Grep"` + srt `ro` config (WC `denyWrite`, narrow Claude-state write set);
  - verified by the WC tree hash and by `projects/<wc-slug>/` holding only `<uuid>.jsonl` with an empty `memory/`.
- **O2 — same session.** `--session-id <uuid>` → exit → `--resume <uuid>`. Same `session_id` in both `init`/`result` events. Context carried over. Tool set and sandbox changed on resume.
- **O3 — cross-run Claude state, cleanup part.**
  - `claude project purge -y <wc>` + exact `session-env/<uuid>` + exact `/tmp/claude/claude-<uid>/<wc-slug>` removal after each run;
  - Pro login unaffected; purged session no longer resumable;
  - preflight that `~/.claude/projects/` is empty.
- **O4 — hidden material.** Harness root `denyRead` in the agent sandbox, re-allowing only the run's WC and TMPDIR. Canary unreachable through Read, Bash and listing. Other runs' WCs and `/mnt/c` also unreachable.
- **O6 — envelope.**
  - `bypassPermissions`;
  - `--tools "Bash,Read,Edit,Write,Glob,Grep"`;
  - `--strict-mcp-config`;
  - `--settings '{}' --setting-sources ""`;
  - srt `impl` config;
  - auth vars unset; `DISABLE_AUTOUPDATER=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`.

  Identical for C0, C1 and C2 phase 2, and asserted from `init` per invocation.
- **O7 — delivery and output.** Prompt via stdin. `--output-format stream-json --verbose`.

### STILL BLOCKS MINIMAL HARNESS

- **Credential file readable by the agent (§5 / F9).**
  - Observed: `~/.claude/.credentials.json` is readable from inside the agent sandbox, because the whole CLI runs in `srt` and needs that file. `denyRead` would break the Pro login.
  - This decides the sandbox layer of the skeleton, so it must be settled first. Either:
    - a topology change, e.g. CLI outside `srt` with per-tool sandboxing, which must then be re-verified for every tool surface; or
    - an explicit, recorded protocol amendment that accepts it.

  The spike did not attempt a workaround.
- **4 pre-existing setup smoke projects in `~/.claude/projects/`.**
  - They are listable/readable by agents and would fail the "projects empty" preflight.
  - Needs a one-time user decision: purge them with `claude project purge -y <each /tmp/cclab-claude-smoke-… path>`, or keep them and accept them in the preflight.

### DEFERRED UNTIL FINAL FREEZE

- **O5** — model pin. `init.model` does report the resolved model ID.
- **O8** — usage/token fields. Field names observed are listed in Spike C, but their stability and meaning are not assessed.
- **Auto-memory.**
  - Whether to set `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` in the envelope. The string exists in the 2.1.263 binary (4 hits), but its behavior is not verified.
  - Not blocking: the memory dir is per-WC, empty at start and purged. The phase-1 content check covers C2.
- **O9** — dependency preparation / cache ignore lists.
- **O10** — temp isolation beyond the exact `/tmp/claude/claude-<uid>/<wc-slug>` removal. `/tmp/claude` is shared by all runs.
- **O11** — limit / auth-failure detection.
- **O12** — caps.
- **O13** — rerun policy.
- **O14** — CLAUDE.md scope.
- **O15** — refactor structural check.
- **O16** — order constraint.
