# Harness WSL Execution Gate — HARNESS_SMOKE_ONLY

Status: **PASS, 2026-09-25.** One real, non-benchmark, single-configuration (C0) run executed
end-to-end under WSL as `cclab`, then cleaned up. This gate proves the skeleton works in its
real execution environment before any pilot is authored. It is **not** a pilot, not one of the
six final tasks, and not part of the 54-run campaign.

## Purpose

Replace the previously-dry execution edges (a real `AgentRunner` and `CleanupRunner`, a
fail-closed run-start preflight, a CLI entry point) and demonstrate one full lifecycle:
`PREPARE → PREFLIGHT → AGENT → CAPTURE FINAL STATE → EVALUATE → CAPTURE RESULTS → PURGE →
EXACT CLEANUP → DONE`.

## Exact boundary tested

- Fixture: `fixtures/harness-smoke` (a trivial `calc.py` with `add`; the smoke task is "add
  `multiply(a, b)`"). No hidden benchmark material.
- Configuration: **C0 only**. C2 mechanics were already proven independently
  (`docs/HARNESS_READINESS_SPIKE.md`); this gate validates the end-to-end harness path.
- Model: `haiku` — a **provisional infrastructure value, explicitly non-final**; it does not
  freeze the O5 model pin.
- Security: the Candidate-2 policy (`docs/CREDENTIAL_ISOLATION_CANDIDATE2.md`), rendered by the
  harness (outer `srt` with `allowAllUnixSockets` + narrow write set, inner sandbox settings,
  `Read()`/`Edit()` credential denies, per-WC settings seeding, sanitized env).
- Auth: existing persisted Claude.ai Pro login via the sanitized invocation path. No API key,
  no alternate billing.

## WSL-native offline checks (model-free)

Run as `cclab` under WSL Python 3.14 (no pytest needed):

- package import + schema load: OK.
- implementation-envelope equality C0==C1==C2: OK.
- cleanup-plan generation (exact scoped targets): OK.
- workspace creation + baseline hash: OK.
- **srt canary probe** (proves the hidden/evaluator boundary without a model call): with the
  real outer `srt` config, `cat hidden/CANARY.txt` was **denied** (rc 1, canary bytes absent)
  while `cat <wc>/calc.py` **succeeded** (rc 0) → the harness root is hidden, the working copy
  is exposed.

The Windows pytest suite (86 tests) also passes; the four POSIX-path-specific behaviors are
additionally exercised by the WSL-native checks above.

## Preflight result

`run_start_checks()` — all fail-closed, all **PASS** for the real run:
`ancestor_instruction_files`, `user_level_instructions` (no `~/.claude/CLAUDE.md`/skills),
`working_copy_unmodified` (fresh copy, seeded `.claude` excluded), `no_project_state`
(fresh opaque WC → no inherited per-project auto-memory), `no_session_env`, `no_tmp_slug`.

## Real smoke run

- run_id: `run_g2jyhx4gyuj2c3g5ub5magbuei`
- workspace_token (opaque): `4deac355baf8a57a`
- security_policy_hash: `c4cc6cab82cb5e82…`
- requested model (NON-FINAL): `haiku`
- session id: `<session-uuid>` (one fresh session; `--session-id`)
- **Real Claude calls: exactly 1.**

### Lifecycle result

`run_validity=valid`, `agent_outcome=completed`, `agent_exit_code=0`, duration ≈ 8.1s,
`session_continuity_verified=true`, `c2_protocol=not_applicable`. Server-side Pro inference
succeeded. The manifest remained immutable (a separate `result.json` holds observations).

### Evaluator result

Ran after agent termination, on a **copy** of the final working copy (agent state not mutated):
`acceptance=pass` (`def multiply` added), `regression=pass` (`add` intact), `integrity=clean`,
`evaluator_error=false`.

### Workspace

`changed_files.json`: `calc.py` modified; nothing added/deleted. The pristine fixture was
unchanged (0 `def multiply`). Opaque path naming intact.

### Artifacts / secret-safety

Allowlisted artifacts produced: `manifest.json`, `result.json`, `preflight.json`,
`changed_files.json`, `evaluator.json`, `events.jsonl`, `stdout.txt`, `cleanup.json`. A full
scan of the results dir for `sk-ant-`, the run canary, and `.credentials.json` found **none**.
No environment or credential dump exists.

### Cleanup

All three exact-scoped commands exited 0 (`executed=true`, `cleanup_failed=false`):
`claude project purge -y <wc>`, `rm -rf -- ~/.claude/session-env/<uuid>`,
`rm -rf -- /tmp/claude/claude-1001/<wc-slug>`. Post-run residue checks: the WC project dir,
the session-env dir, and the runs working copy are all absent. Unrelated historical smoke
projects were left untouched. Auth after the run: `loggedIn=true, authMethod=claude.ai,
apiProvider=firstParty, subscriptionType=pro`; credential file mtime unchanged.

## Provenance fix applied during the gate

The gate surfaced that `make_working_copy` minted its own token instead of using the manifest's
`workspace_token`, so the recorded token and the on-disk WC dir differed (both opaque; not a
security issue, but a provenance mismatch). Fixed: the lifecycle now threads
`manifest.workspace_token` into `make_working_copy`, so the WC directory name equals the
recorded token. Verified by unit test and a WSL dry run (WC dir == manifest token). No second
real call was needed.

## Limitations

- Model/timeout/usage semantics remain OPEN (O5/O8/O12); the smoke `haiku` value is
  infrastructure-only and must not become a default.
- Subscription-limit and auth-failure detection used string/`error_status` heuristics (O11) at the
  time. Since G4 (2026-09-28) they read structured CLI fields only (`docs/G4_OUTCOME_CLASSIFIER.md`).
  A `rate_limit_event` in the stream is informational and is not treated as a limit interruption.
- The smoke run's artifacts are disposable and were removed with the smoke root after capture;
  the identifiers above are the record.
- Non-credential contamination detection is real for this run's own WC/session/slug; broader
  cross-run transcript/memory isolation (O3) and hidden-material placement for real tasks (O4)
  are still to be finalized when tasks are authored.

## Decision

`PASS` — the harness performs a real HARNESS_SMOKE_ONLY C0 run end-to-end under WSL as `cclab`,
with Candidate-2 protection active, correct evaluator/cleanup boundaries, no secret leakage, and
auth intact.
