# G5s — Evaluator sandbox (2026-09-28)

Status: **RESOLVED.** The model-free WSL behavioral matrix passed as `cclab`. No Claude call was
made, and the real credential file was never opened.

## Threat model and boundary

Agent-written repository code is **untrusted** while evaluator checks run. The evaluator sandbox
is its own trust boundary: it shares no settings with the Candidate-2 agent sandbox (no Claude
state, no Anthropic domains, no `allowAllUnixSockets`).

```
harness (Python, outside): copy candidate -> restore protected paths -> inject hidden tests
  run_with_deadline([srt, -s, <root>/srt-eval.json, --, *check.argv], cwd=<root>/wc)   (G1)
    srt 0.0.77 (node, outside) -> sh -> bwrap --new-session --unshare-pid/net/user -> check
```

Harness Python never runs inside the sandbox. `<root>` is a fresh `cclab-taskeval-*` temp dir.
Only `<root>/wc` (the evaluator copy) and `<root>/home` (the check's HOME/TMPDIR) are visible to
the check. The srt config (`<root>/srt-eval.json`) and srt's own sockets (`<root>/srt-tmp`) are not.

Code: `src/codeagent_configlab/evaluator_sandbox.py` (`production_evaluator_sandbox`) plugs into
`TaskEvaluator.sandbox`, the former `command_wrapper` seam.

## Policy (`g5s-v2`; v2 adds the G8 check launcher)

| | Paths |
|---|---|
| read + write | evaluator copy `<root>/wc`, private `<root>/home` (`HOME`, `TMPDIR` via `CLAUDE_CODE_TMPDIR`) |
| read-only | `/usr`, `/bin`, `/lib`, `/lib64`, `/etc`; the single file `~/.nvm/versions/node/v22.23.2/bin/node`; srt's `vendor/seccomp/x64/apply-seccomp` (needed to apply the AF_UNIX filter) |
| hidden | everything else (`denyRead: ["/"]`). Explicitly named as well: harness root, pristine, hidden source, results root, credential path, `/mnt/c`, `/tmp/claude/*` |
| write-denied | `/tmp/claude` (srt always binds it; it is shared with agent runs) |
| network | none: `allowedDomains: []` → `--unshare-net`; AF_UNIX `socket()` blocked by seccomp |
| PATH | `<node bin>:/usr/local/bin:/usr/bin:/bin` (host PATH is not inherited) |

Writes to hidden locations may succeed **inside** the sandbox, because srt's read-deny tmpfs is
writable. They never reach the host. This is proven by exact host snapshots, not by errno.

## Provenance

`evaluator.json.sandbox` = `{kind: "srt", version: "g5s-v2", policy_hash, identity,
production_safe: true}`.

- The identity is built from roles, the task layout and the pinned toolchain. It never includes
  the configuration or per-evaluation temp names, so C0 = C1 = C2 for a task. This is asserted in
  both the pure test and the lifecycle test.
- The credential path is recorded only as `credential_path_sha256`, because the artifact
  secret-scan refuses credential file names.
- WSL policy hash for the probe layout: `82ac942a315175563537ae687843d607ad6e356ae585b086e8917791ffed9c08`
  (`g5s-v2`; was `78f7cc1e…45ef48dd` under `g5s-v1`). The hash is layout-specific;
  each real task gets its own hash, identical across configurations.

## Fail closed

- **No sandbox** → `evaluator_error`, nothing executed.
- **Initialization errors** → `evaluator_error`, no check run, never retried, never run unsandboxed.
  This covers: not Linux / no `/proc`, missing srt/node/seccomp/python/bwrap, srt version ≠
  0.0.77, an evaluation root overlapping a protected path, or a check program that doesn't resolve.
- **Preflight** (a sentinel inside the same sandbox that also checks each check program is
  executable there) failing → `evaluator_error` for every check, with srt's diagnostics kept.
- **Post-flight** failing after the checks → `evaluator_error` (verdicts voided).
- A normal nonzero exit remains `fail` on its axis; a timeout remains `fail`; termination failure
  remains `error` (G1, unchanged).
- The Windows `subprocess.run` branch exists only without `/proc`, and the srt sandbox refuses to
  prepare there. The Windows suite uses a test double (`tests/_helpers.FakeSandbox`) whose record
  says `production_safe: false`.

## WSL behavioral matrix (`spike/g5s-evaluator-sandbox/g5s_probe.py`, fixture `fixtures/evaluator-security`)

| Probe (Python and Node) | Result |
|---|---|
| sandbox startup, 7 checks (3 acceptance, 2 structural incl. Node, 2 regression incl. `node --test`) | all `pass`, `evaluator_error=false` |
| evaluator copy read/write, private TMPDIR, Python and Node child processes, injected hidden tests readable in the copy | allowed |
| read: harness canary, hidden source, pristine, results, fake credential, HOME canary, another evaluation copy, `/tmp/claude` canary, real harness repo (`/mnt/c`), symlink escape, `/proc/1/root`, `/proc/<harness>/root`, `/proc/<harness>/environ` | all blocked |
| stat real credential, `~/.claude`, harness root | not visible |
| listings: HOME shows only the `.nvm` mount skeleton; `/mnt/c` absent; `/run` empty; `/tmp/claude/claude-1001` empty | ok |
| TCP connect to host `127.0.0.1` listener (Python and Node); AF_UNIX socket | refused / blocked; listener saw 0 connections |
| timeout: check ignoring SIGTERM + grandchild in a new session ignoring SIGTERM, cap 2 s | `fail`, `timed_out`, not an evaluator error, 0 survivors (3.5 s) |
| mutation containment: exact hashes of probe root (harness, pristine, hidden, results, canonical candidate, fake credential, HOME canary), other evaluation copy, host `/tmp/claude` | identical before/after |
| residue after probe | none |

Tests: `tests/test_evaluator_sandbox.py` (20 tests: pure + real srt, A–R) and
`tests/test_task_evaluator.py` (fail-closed tests with the fake). WSL:
`PYTHONPATH=src:tests python3 -m unittest tests.test_evaluator_sandbox -v`.

## Limitations

- **`/tmp/claude` names are visible.** Top-level entry *names* under `/tmp/claude` can be listed.
  Contents are denied, subdirectories appear empty, and the directory is not writable. srt 0.0.77
  always binds it.
- **Visible system paths.** `/etc`, `/usr` and `/sys` are readable (read-only system data, no
  secrets).
- ~~Mid-run srt failure~~ **closed by G8.** Each check runs as
  `sh -c '…"$@"; rc=$?; printf "
CCLAB-EVAL-RC:<nonce>:%s
" $rc'` inside the sandbox. Without that
  trailer as the last stdout line, matching the process exit code, the check is `error`
  (evaluator infrastructure), never `fail`. Verified on WSL with a real srt that dies for one check.
  Agent code that kills its own launcher also ends up as `error` (fail-closed; reviewed on
  re-evaluation).
- ~~Output tails and the secret scan~~ **closed by G8 for `evaluator.json`.** Offending strings are
  withheld with a size-only placeholder (`output_withheld`) and the verdict stands. Agent-artifact
  capture was closed by G12 (`ArtifactStore.write_safe`, shared `withhold_markers`).
- **Pinned layout.** The toolchain paths assume the pinned nvm Node 22.23.2, srt 0.0.77 and x64 WSL.
  Any change makes `prepare` fail closed.
