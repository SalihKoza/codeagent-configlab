# CodeAgent ConfigLab — Credential-Isolation Spike, Candidate 2

Status: **infrastructure spike, 2026-09-25.** Not a benchmark task, no research value.
Tests a second candidate topology for the blocker in `docs/HARNESS_READINESS_SPIKE.md`
("Credential file readable by the agent"), after Candidate 1
(`docs/CREDENTIAL_ISOLATION_SPIKE.md`) was NO-GO.

Environment: WSL2 Ubuntu, user `cclab`, Claude Code **2.1.263** (native ELF),
sandbox-runtime (`srt`) 0.0.77, bubblewrap 0.11.1, ripgrep 15.1.0, persisted Claude.ai
**Pro** login (verified `loggedIn/claude.ai/firstParty/pro` before and after; credential
mtime `1790335347`, unchanged across the spike). No API key, no other provider.

Evidence: `spike/credential-isolation-candidate2/spike.sh`; WSL artifacts in
`~/cclab-cred2/artifacts/` (`cap.log`, `nest.log`, `m.jsonl`/`m.err`/`m-debug.log`,
`p1.*`, `p2.*`, `w.jsonl`, `t.jsonl`, `hostcanary.log`).

Real Pro calls: **7** short `haiku` calls — `m` ×3 (config iterations), `p1`, `p2`,
`wprobe`, `tprobe`. No usage limit hit. Plus model-free `sandbox status` / `srt` probes.

Labels: **[obs]** observed this spike · **[inf]** inference · **[doc]** 2.1.263 binary /
srt source text (schema/comment), not itself behavioral.

---

## Candidate definition

Candidate 1 ran the whole `claude` CLI inside the outer `srt` **unchanged**, and Claude's
inner Bash sandbox could not initialize because the outer AF_UNIX seccomp filter blocked
the inner runtime's `listen()` on `/tmp/claude/srt-mux-*.sock`.

**Candidate 2 is a different trust topology**, not a patch of Candidate 1. It deliberately
relaxes exactly one outer boundary — the AF_UNIX block — so the inner sandbox can start,
then relies on the **inner** sandbox to re-establish the model-controlled boundary and on
**permission deny rules** for the built-in file tools. The trusted CLI process gains the
Unix-socket capability it needs; model-controlled Bash/subprocesses must not.

```
outer srt = Candidate-1 "narrow" ro/impl  +  ONE delta: network.allowAllUnixSockets:true
  └─ claude -p            (trusted: reads real creds; may use the srt-mux Unix socket)
       ├─ inner Claude Bash sandbox (per-command bwrap + AF_UNIX seccomp) ← model Bash
       └─ permissions.deny Read()/Edit() + sandbox.credentials.files deny ← built-in tools
```

## Outer-policy delta

Exactly one line changes versus Candidate 1, confirmed by diffing the configs [obs]:

```
  "network":{"allowedDomains":[...5 Anthropic hosts...],"deniedDomains":[]
+                                                       ,"allowAllUnixSockets":true }
```

No other outer protection changed. Still enforced under the relaxed config [obs, `nest.log`
+ direct probes]:
- harness/spike root `denyRead` (tmpfs) — `cat $SP/fixture/calc.py`, `cat $SP/state.env`,
  other-run WC all → `No such file or directory`; identical to the norelax baseline;
- `/mnt/c` hidden — `ls /mnt/c` empty, `cmd.exe` path absent;
- network allowlist unchanged;
- writable-path restriction unchanged.

**Why the delta is coarse (not a design choice).** [doc, srt
`linux-sandbox-utils.js:2370`] "The allowUnixSockets configuration is not path-based on
Linux … seccomp cannot filter by path." The only Linux control is the boolean
`allowAllUnixSockets`, which [doc `:2422-2434`] skips the whole AF_UNIX seccomp filter.
There is **no path-scoped Unix-socket relaxation on Linux**; this boolean is the minimum
possible. It widens the *trusted* process's capability (it could reach the WSL interop
socket); the isolation argument is that model-controlled code is separately re-confined by
the inner sandbox (tested in the Unix-socket matrix below).

## Installed-version capability matrix

| # | Mechanism | Evidence | Status |
|---|---|---|---|
| 1 | Inner Bash sandbox initializes inside relaxed outer | [obs] no `Failed to initialize sandbox`/`srt-mux` in any of 5 model runs' debug logs; [obs] `srt -s outer(relax) -- srt -s inner -- true` rc 0 | **SUPPORTED** |
| 2 | `allowUnsandboxedCommands:false` | [obs] `dangerouslyDisableSandbox:true` on a denied path still `permission_denied`; [doc] "dangerouslyDisableSandbox parameter is completely ignored" | **SUPPORTED** |
| 3 | `failIfUnavailable:true` | [obs] no init failure occurred in Candidate 2 (relaxation fixed it), so fail-closed was not exercised at the tool boundary; [doc] error string present | UNCLEAR (not triggered; sandbox stayed available) |
| 4 | `sandbox.credentials.files` deny exists & enforces (Bash) | [obs] python `open()`→`PermissionError [Errno 13]`, node→`EACCES`, `grep -r`/`find -exec cat`→`Permission denied` on the fake | **SUPPORTED** (OS-level EACCES) |
| 5 | `sandbox.filesystem.denyRead` | [obs] belt-and-braces with #4; same EACCES results | SUPPORTED |
| 5b | `sandbox.filesystem.allowWrite` **required** for a usable WC | [obs] without it every Bash command dies `bwrap: Can't create file at <WC>/.claude/settings.json: Read-only file system`; with `[WC,TMPDIR]` Bash runs | SUPPORTED (mandatory) |
| 6 | Built-in `Read(//abs)` deny | [obs] Read of fake → `File is in a directory that is denied by your permission settings` | **SUPPORTED** |
| 7 | Built-in `Edit(//abs)` deny | [obs] Edit of fake → denied; Edit of `calc.py` works | **SUPPORTED** |
| 8 | `Write(path)` deny rules | [obs, Candidate 1] `[WARN] Write(...) is not matched by file permission checks — only Edit(path) rules are` | **UNSUPPORTED / inert** (Write covered by Edit rule + directory-deny) |
| 9 | Grep/Glob honor the Read deny | [obs] Grep/Glob of fake → `No matches found` / `No files found` (silent) | SUPPORTED but **best-effort** (permission layer, not OS; see Limitations) |
| 10 | `--setting-sources ""` excludes WC settings; operator posture wins | [obs] `sandbox status` from a WC whose `settings.local.json` says `enabled:false` reports `enabled:true, strictMode:true, enabledSource:policy` — both with AND without `--setting-sources ""` | **SUPPORTED** |
| 11 | Agent cannot weaken active protection from the WC | [obs] agent overwrote `settings.json`/`settings.local.json` (sandbox off + `permissions.allow:["Read(**)"]`); reload logged "Replacing all allow rules for projectSettings/localSettings with 0"; credential stayed denied | **SUPPORTED** (tamper inert) |
| 12 | Coarse `allowAllUnixSockets` is the only Linux Unix-socket knob | [doc] srt source #Delta above | SUPPORTED (documented constraint) |

## Inner sandbox startup

**PASS.** [obs]
- Candidate 1 reproduction (norelax): `srt -s outer -- srt -s inner -- true` → rc 1,
  `listen EPERM … /tmp/claude/srt-mux-2-0.sock`.
- Candidate 2 (relax): same nesting → rc 0. In all 5 model runs, debug logs contain **no**
  `Failed to initialize sandbox` and **no** `srt-mux` error.
- `claude --settings <PROTECT> --setting-sources "" sandbox status` inside the relaxed
  outer → `enabled:true, strictMode:true, enabledSource:policy, unavailableReason:null`.

## Bash/subprocess matrix

Fake fixture `~/cclab-cred2/fake-home/.claude/.credentials.json` (mode 600, canary
`CRED2-CANARY-<hex>`), configured identically to the real path (§ equivalence). All from
model-controlled Bash [obs, `m.jsonl`]:

| Probe | Result | Verdict |
|---|---|---|
| `cat` / `head -c` / `tr < ` fake | `permission_denied` (command-analysis layer) | DENIED |
| `python3 open()` fake | `PermissionError [Errno 13] Permission denied` | DENIED (OS/EACCES) |
| `node fs.readFileSync` fake | `Error: EACCES: permission denied` | DENIED (OS/EACCES) |
| `grep -r CRED2-CANARY fake-home` | `Permission denied` on the file | DENIED (OS/EACCES) |
| `find … -exec cat {}` | `Permission denied` | DENIED (OS/EACCES) |
| **positive**: `python3 -c 'print(6*7)' && echo …` | `42 | BASH-POSITIVE-OK` (err=False) | WORKS |
| **positive**: workspace Edit + Write (absolute paths) | `calc.py` gained `multiply`, `created.txt`=WPROBE-OK persisted | WORKS |

Both the OS layer (credentials.files/denyRead → EACCES) and the command-analysis layer
(deny rule matched in the command string) block credential reads; positive controls pass.

## Unix-socket regression matrix

The point of Candidate 2: prove the inner sandbox re-blocks what the outer relaxation
opened. All from model-controlled Bash [obs, `m.jsonl`], plus a model-free A/B [obs,
`nest.log`]:

| Probe | Outer-relax alone (trusted view) | Inner sandbox (model view) | Verdict |
|---|---|---|---|
| create `AF_UNIX` socket | `AF_UNIX-created` | `PermissionError`/socket error, `AFUNIX-OK` never printed | **re-blocked** |
| connect `/run/WSL/*_interop` | (would connect) | fails at `socket()` creation, `INTEROP-CONNECTED` never printed | **re-blocked** |
| `cmd.exe /c echo <PWN>` | n/a | `command not found` (127); `<PWN>` never appears as output | not executed |
| connect host canary socket (`$TMP/hostcanary.sock`, listener live) | (would connect) | socket-creation error; `hostcanary.log` INBOUND count = **0** | **re-blocked** |

**Attribution (per §12):** the interop block is not merely PATH absence. Two independent
barriers: (a) `/mnt/c` hidden → no `.exe` and `cmd.exe` not on PATH; (b) even connecting
directly to the interop socket path fails at `socket(AF_UNIX,…)` creation — the inner
seccomp filter. `binfmt_misc` interop invokes `/init`, which must open an AF_UNIX socket to
`/run/WSL/*_interop`; with AF_UNIX blocked inside the sandbox, no Windows process can be
launched even if a reachable `.exe` existed.

**Result: no host/Windows escape from model-controlled code.**

## Fallback behavior

[obs] `Bash{dangerouslyDisableSandbox:true}` reading the fake → `permission_denied`
(same as without the flag). No `unsandboxed`/`fallback` markers in any debug log. No
Bash command ran outside the sandbox. `allowUnsandboxedCommands:false` held.
`failIfUnavailable:true` was not exercised (the sandbox never became unavailable in
Candidate 2), so its fail-closed behavior at the tool boundary remains UNCLEAR — but it is
not needed here because the sandbox stayed available in every run.

## Built-in file-tool matrix

[obs, `m.jsonl`] fake = credential fixture; positive control = `calc.py`:

| Tool | Direct fake | Symlink (see below) | Positive control | Verdict |
|---|---|---|---|---|
| Read | `directory … denied by your permission settings` | `Read(...) has been denied` (rule) | `calc.py` read OK | DENIED (rule) |
| Grep | `No matches found` (fake contains the canary) | `No matches found` | `def add` matched | DENIED, **silent/best-effort** |
| Glob | `No files found` | `No files found` | `*.py`→`calc.py` | DENIED, **silent/best-effort** |
| Edit | `directory … denied` | (n/a) | `calc.py` edited + persisted | DENIED (rule) |
| Write | `directory … denied` | (n/a) | `created.txt` written + persisted | DENIED (rule) |

Read/Edit/Write are denied by an explicit permission rule (hard error). Grep/Glob **skip**
the denied path silently (no error, no content) — effective here but permission-layer
best-effort, not an OS guarantee (see Limitations).

## Symlink tests (mandatory)

[obs, `m.jsonl`] The agent created `lnk.json → fake` and `lnkdir → fake dir` (Bash succeeded):

| Access via symlink | Result | Verdict |
|---|---|---|
| Bash `cat lnk.json` | `permission_denied` (analysis resolved the target) | no bypass |
| Bash `python3 open('lnkdir/.credentials.json')` | `bwrap: Can't create file … No such file or directory` (credential bind fails on the aliased path) | no bypass |
| Read `lnk.json` | `Permission to read … lnk.json has been denied` (rule) | no bypass |
| Read `lnkdir/.credentials.json` | `directory … denied` | no bypass |
| Grep `lnkdir` / Glob `lnkdir` | `No matches` / `No files` | no bypass (silent) |

The deny rules target the real credential path; no symlink route returned any canary byte.
**No viable symlink bypass.**

## Settings tampering

[obs] The agent successfully overwrote the (seeded) WC `settings.json` and
`settings.local.json` with `sandbox.enabled:false` + `permissions.allow:["Read(**)","Bash"]`.
Effect on protection: **none.**
- Immediately afterwards, `cat`/Read of the fake were still denied.
- The reload logged `Replacing all allow rules for destination 'projectSettings'/'localSettings' with 0 rule(s)` — WC settings contribute nothing under `--setting-sources ""`.
- Model-free confirmation: `sandbox status` from a WC bearing `settings.local.json:{enabled:false}` reports `enabled:true, strictMode:true, enabledSource:policy` **with and without** `--setting-sources ""`. The operator posture (the `--settings` flag = policy level) cannot be overridden by project/local settings.

**Precedence observed (2.1.263):** managed/flag(`--settings`) = policy, wins; user; project;
local. `--setting-sources ""` drops user/project/local entirely. Operator-posture keys
(`sandbox.enabled`, `allowUnsandboxedCommands`, `failIfUnavailable`) additionally cannot be
weakened by project/local even when those sources are loaded.

**Requirement discovered:** the protection config is delivered only via the `--settings`
command-line flag (not from any agent-writable file), which is the non-agent-writable
settings source the candidate needs. **However**, each WC must be pre-seeded with an (empty)
`.claude/settings.json` + `settings.local.json`, or Claude's Bash-tool bwrap cannot create
its settings mount point and **every Bash command fails** (`Can't create file at
<WC>/.claude/settings.json`). These seeded files are agent-writable and watched, but — as
shown above — cannot weaken protection.

## Real credential-path equivalence

[obs] `protect.json` lists `/home/cclab/.claude/.credentials.json` in the **same four
places** and shapes as the fake: `sandbox.credentials.files[].path` (mode `deny`),
`sandbox.filesystem.denyRead[]`, `permissions.deny "Read(//…)"`, `permissions.deny
"Edit(//…)"`, plus the shared `Read(**/.credentials.json)`/`Edit(**/.credentials.json)`
globs. The debug log shows all rules loaded ("Adding … deny rule(s) to 'flagSettings'").
Real-file metadata (mode 600, owner cclab, mtime `1790335347`, inode `2096:36850`) was
unchanged from start to finish. The file was never `cat`/Read/grep/hash/size/copy/parse'd.

Enforcement was demonstrated on the fake, which is configured **identically** (same
basename, same `.claude/` parent shape and mode/owner, same filesystem, same policy
entries, same outer-sandbox rights). Real-path enforcement is therefore **[inf]** from
structural + rule-loading equivalence — the strongest evidence obtainable without reading
the secret; the actual per-tool denial on the real path is not separately re-observed.

## Auth and C2 regression

[obs] `p1` then `p2`, one session:
- Phase 1 (`--session-id`, tools `Bash,Read,Glob,Grep`, `ro` outer, PROTECT): WC hash
  before == after (repository unchanged); fake denied via Bash and Read; plan produced;
  `session_id = 5b33c20b-…`.
- Phase 2 (`--resume`, tools `Bash,Read,Edit,Write,Glob,Grep`, `impl` outer, PROTECT): same
  `session_id` in init and result; `calc.py` gained `multiply(a,b)`; `output.txt` =
  `HERON-CRED2` (carried context across resume); fake still denied.
- No unsandboxed execution; no `srt-mux` failure; canary count 0 in both phases' jsonl,
  err, debug, transcript, and both WCs. Auth after: `loggedIn/claude.ai/firstParty/pro`.

(Write-persistence note: an earlier adversarial run using relative paths **and** disabling
the sandbox mid-run via the tamper showed Edit/Write reporting success without persisting;
the clean `wprobe` and `p2` runs — absolute paths, no tamper — persisted reliably, so the
anomaly is attributed to the mid-run sandbox-disable, not to normal operation.)

## C0/C1/C2 equality

The credential-isolation control is a common environmental control, applied identically:
- one `protect_json` output (byte-identical up to the per-run WC/TMPDIR paths, which are
  path-shape-identical exactly as the existing envelope already varies them) passed as
  `--settings` with `--setting-sources ""` to C0, C1, C2-phase-1 and C2-phase-2;
- identical outer `allowAllUnixSockets:true` relaxation for all;
- identical per-WC seeding of empty `.claude/settings.{json,local.json}`.
Only C2 phase 1 differs — in `--tools` and the `ro` outer config — which is its intended
planning treatment, not a credential-isolation difference. **Equality holds.**

## Limitations

- **Outer OS sandbox (bwrap, verified):** filesystem confinement (hidden material,
  `/mnt/c`, other runs) is unchanged by the relaxation — the relaxation touches only the
  seccomp AF_UNIX filter, and filesystem policy is enforced by bwrap mounts, verified
  identical relax vs norelax.
- **Inner OS sandbox (bwrap + seccomp, verified):** for model-controlled **Bash and its
  subprocesses**, credential reads fail with EACCES and AF_UNIX (hence interop/host sockets)
  is blocked at the syscall layer. This is the strong guarantee.
- **Permission-layer (not OS) for built-in tools:** Read/Edit/Write denial is a hard rule
  error; **Grep/Glob** silently skip the denied path. These tools run in the main process,
  where the outer sandbox *allows* reading the credential (the CLI needs it), so their
  credential protection rests on the permission layer alone — best-effort, not OS-backed.
  No observed bypass, but weaker than the Bash guarantee.
- **Coarse relaxation:** `allowAllUnixSockets:true` grants the *trusted* process full
  AF_UNIX capability (Linux has no path-scoped option). The isolation depends entirely on
  the inner sandbox re-blocking model-controlled code, which was verified.
- **Operating requirement:** every WC must be pre-seeded with empty
  `.claude/settings.{json,local.json}` or Bash is unusable; those files are agent-writable
  and watched but proven unable to weaken protection.
- **Real-path enforcement:** [inf] from structural + rule-loading equivalence; not
  separately re-observed on the real file (by design — reading it is forbidden).
- **Not tested / UNCLEAR:** `failIfUnavailable` fail-closed at the tool boundary (never
  triggered); ptrace/`process_vm_readv`/core-dump attacks on the CLI process; hard links
  across filesystems; MCP/WebFetch/Task tools (not in `--tools`); non-`haiku` models;
  auto-memory content beyond the empty per-WC dir.

## Final decision

`GO — Candidate 2 is sufficient for V0 minimal harness`

Deciding evidence: with the single outer delta `allowAllUnixSockets:true`, (1) Claude's
inner Bash sandbox initializes reliably [no `srt-mux` failure in 5 runs]; (2) model-
controlled Bash cannot read the fake credential [EACCES from python/node/grep/find] and
cannot use AF_UNIX, WSL interop, or a host socket [socket-creation blocked; interop 127;
host INBOUND 0]; (3) the unsandboxed fallback is disabled [`dangerouslyDisableSandbox`
still denied]; (4) built-in Read/Edit/Write are denied by rule and Grep/Glob return nothing
[no canary in any artifact]; (5) no symlink bypass; (6) WC settings tampering cannot weaken
protection [operator posture `enabledSource:policy` with and without `--setting-sources ""`];
(7) the C2 phase-1/phase-2 resume flow works with credential protection active and Pro auth
intact; (8) the control is identical across C0/C1/C2. The candidate carries two operating
requirements (per-WC settings seeding; coarse Unix-socket relaxation offset by inner
re-confinement) and one weaker layer (Grep/Glob best-effort), all documented above and none
of which permitted a credential read or a host escape in testing.
