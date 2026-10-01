# Run Manifest & Result Contract — V0

Status: **skeleton contract, 2026-09-25.** Defines the two records the minimal harness writes
per run. It implements the artifact fields of `docs/EXPERIMENT_PROTOCOL_V0.md` §6/§7 and the
status axes of §6; it does not add or relax any frozen decision. Schemas:
`schemas/run-manifest.schema.json`, `schemas/run-result.schema.json`. Code:
`src/codeagent_configlab/{manifest,result,status}.py`.

## Immutable specification vs observed result

A **run** is one `(task, configuration, repetition)` cell executed once (protocol §2). Its record
is split in two, deliberately:

- **`manifest.json`** — the *planned inputs*. It is the source of truth for what the run was
  supposed to be. In code it is a **frozen** dataclass (`RunManifest`); once built it cannot be
  mutated. Runtime results never write back into it.
- **`result.json`** — the *observed outputs*. Written after the run. Separating the two prevents
  runtime results from silently mutating the experimental specification.

Both are validated against their JSON Schema by a small stdlib validator
(`schema.py`) — no third-party dependency, so the harness runs as `cclab` in WSL with no pip.

## Absence semantics: `OPEN` vs `null`

Two different absences are represented explicitly, never with a fake value:

| Meaning | Encoding | Example |
|---|---|---|
| **OPEN** — decision undecided, must be frozen before final runs (protocol §12) | JSON string `"OPEN"` (visibly not a real value) | `model_request` (O5), `effort_request`, `timeout_seconds` (O12) |
| **N/A** — field does not apply to this configuration | JSON `null` | `planning_tool_set` on a C0 run |

Rationale: a plausible-looking default could accidentally become the frozen value, so OPEN is a
visible sentinel rather than a guess. `model_request` is always a string (either `"OPEN"` or a
model id), so its OPEN-vs-frozen state is semantic; `timeout_seconds` is `"OPEN"` or a number.

## Manifest fields (`run-manifest/v0`)

| Field | Meaning / rule |
|---|---|
| `schema_version` | const `"run-manifest/v0"`; see versioning below |
| `run_id` | opaque per-attempt id (`run_…`); never encodes task/config/rep |
| `task_id` | task identifier (pilot ids are distinct, e.g. `P-…`) |
| `task_version_hash` | content hash of the task/fixture definition |
| `language` | `python` \| `typescript` |
| `task_category` | `bugfix` \| `feature` \| `refactor` |
| `configuration` | `C0` \| `C1` \| `C2` |
| `repetition` | integer repetition number |
| `order_position` | `null` until the run order is assigned; else integer (protocol §11) |
| `order_seed_ref` | `null` until assigned; else a reference to the frozen order seed |
| `workspace_token` | opaque working-copy directory token; encodes nothing (protocol §4/§9) |
| `claude_code_version`, `node_version`, `npm_version`, `sandbox_runtime_version` | frozen version pins, recorded per run (drift is a measured confound) |
| `model_request` | model value passed to the CLI; `"OPEN"` until frozen (O5); the literal `"Default"` is rejected |
| `effort_request` | effort level passed to the CLI via `--effort`; `"OPEN"` until frozen; else one of low/medium/high/xhigh/max |
| `permission_mode` | e.g. `bypassPermissions` (the sandbox is the boundary in headless mode) |
| `implementation_tool_set` | tool allowlist for C0/C1/C2-impl |
| `planning_tool_set` | C2 planning tools; **`null` for C0/C1**, non-null for C2 |
| `settings_policy_hash` | hash of the execution-envelope identity (`ExecutionEnvelope.envelope_hash`) |
| `security_policy_hash` | hash of the Candidate-2 `SecurityPolicy` identity |
| `task_statement_hash` | hash of the byte-identical task statement |
| `claude_md_hash` | **`null` for C0**; non-null for C1/C2 (the treatment file) |
| `planning_wrapper_hash` | C2 planning-wrapper hash; `null` for C0/C1 |
| `approval_message_hash` | C2 approval-message hash; `null` for C0/C1 |
| `timeout_seconds` | wall-clock cap; `"OPEN"` until frozen (O12) |
| `created_at` | ISO-8601 UTC creation timestamp |

Configuration-conditional rules (enforced by `RunManifest.validate` beyond the structural
schema): C0 has `claude_md_hash == null` and all three planning fields `== null`; C1 has a
non-null `claude_md_hash` and null planning fields; C2 has non-null `claude_md_hash`,
`planning_tool_set`, `planning_wrapper_hash`, `approval_message_hash`.

### Series provenance (G10, 2026-09-28; optional, additive within v0)

Present only on series attempts; absent on the smoke and on older records:
- `namespace` (`PILOT` | `HARNESS_SMOKE_ONLY` | `FINAL`), `series_id`, `series_spec_hash`;
- `cell_id` (the planned task × configuration × repetition cell; `run_id` is the *attempt* id);
- `attempt_ordinal` (1 = original), `attempt_kind` (`original` | `replacement`);
- `original_attempt_id`, `predecessor_attempt_id`, `replacement_reason`.

A replacement keeps the cell's `repetition` and every frozen field (`series.frozen_cell_spec_hash`).
`order_position` / `order_seed_ref` are set from the frozen schedule (`schedule_hash`).
`timeout_seconds`, `model_request` and `effort_request` are the executable truth: the lifecycle
refuses a budget, runner model or runner effort that differs from them. Series state itself lives
in `docs/PILOT_SERIES_V0.md` artifacts, not in `result.json`.

## Result fields (`run-result/v0`)

Identity/timing: `run_id`, `started_at`, `ended_at`, `duration_seconds`.
Process: `agent_exit_code`, `phase1_exit_code`, `phase2_exit_code` (the two phase codes are
`null` for C0/C1), `observed_session_id`, `session_continuity_verified`.
Status axes (kept separate, never merged into a score):

| Field | Axis (protocol §6) |
|---|---|
| `agent_outcome` | `completed` \| `error_exit` \| `timeout` \| `limit_interrupted` \| `auth_failure` \| `harness_error` |
| `run_validity` | `valid` \| `invalid:infrastructure` \| `invalid:harness` \| `invalid:fixture` \| `invalid:leak` \| `invalid:carryover` \| `invalid:c2_protocol` \| `preflight_failed` |
| `acceptance` / `regression` | `pass` \| `fail` \| `error` \| `not_run` |
| `integrity` | `clean` \| `protected_path_modified` \| `out_of_tree_write_detected` |
| `c2_protocol` | `ok` \| `phase1_write` \| `phase_transition_failed` \| `not_applicable` |

Classification flags: `invalid_reason`, `interruption_reason`, `limit_interrupted`,
`auth_failure`, `harness_failure`, `evaluator_error`.
Artifacts (`artifacts` object): relative logical refs to `stdout`, `stderr`, `events`,
`final_diff`, `changed_files`, `evaluator` (each `null` if not produced). `cleanup`: `performed`
+ `report_ref`.

**`resolved`** (the V0 primary binary outcome, protocol §6) is *derived*, not stored:
`valid ∧ acceptance pass ∧ regression pass ∧ integrity clean` (`status.is_resolved`). It is a
single boolean, **not** a weighted or composite quality score — V0 defines none.

### Analysis eligibility (G3, 2026-09-28)

`analysis_eligibility = {status, reason}` answers one question: does this attempt count as the
planned observation for its task × configuration × repetition cell? It is **derived**, not
independently set. `RunResult.to_dict()` computes it with `status.derive_analysis_eligibility(run_validity,
agent_outcome)`, and `validate_result_record` recomputes it and rejects any mismatch
(`status.check_status_consistency`). It is stored anyway so that `result.json` is self-describing.

| `status` | when | `reason` |
|---|---|---|
| `countable` | `valid` and `completed` / `error_exit` / `timeout` | `valid_outcome:<agent_outcome>` |
| `not_countable:external_interruption` | `valid` and `limit_interrupted` | `subscription_limit` |
| `not_countable:invalid` | any `invalid:*` or `preflight_failed` | `<run_validity>[/<agent_outcome>]` |
| `not_countable:evaluation_pending` (G8) | `valid`, but `evaluator_error` or a verdict `not_run` | `evaluator_error` / `no_evaluator_verdict` |

The field is additive within `run-result/v0`: it is optional in the schema. It is absent only in
records written before G3, and for those it is derived on read from the two stored axes.
Subscription-limit interruption is an external non-countable execution interruption, not a task
failure and not by itself a protocol/harness-invalid run: `run_validity` stays `valid`.
Authentication failure stays `invalid:infrastructure` (protocol §10). G8 invariants: `evaluator_error` is true exactly when a verdict axis
is `error`; a `pass`/`fail` verdict requires `artifacts.evaluator`. `evaluator.json` may carry
`output_withheld` (diagnostic strings replaced by a size-only placeholder because they tripped the
secret scan) or `finalization_failed` (metadata-only record; verdicts `error`). No composite status
exists; `resolved` is still derived separately, and analysis filters by eligibility first.

### Withheld and unwritable artifacts (G12, 2026-09-28)

Every artifact is written through `ArtifactStore.write_safe`. The secret scanner is unchanged
and authoritative. When content trips it:
- JSON artifacts (`*.json`) and `events.jsonl` are stored with offending strings/keys replaced by
  `[withheld: secret-scan marker; N bytes]`. Event structure (types, session ids, result fields)
  is kept.
- Text artifacts (`stdout.txt`, `stderr.txt`, `plan.txt`, `final.diff`, and the phase variants)
  become a placeholder file naming `content_withheld:secret_policy`.

The artifact still exists and its `result.artifacts` ref is set, so *withheld* is never confused
with *never produced* (ref `null`). `artifact_report.json`, referenced by the optional
`artifacts.artifact_report` (additive within v0), lists
`{name, status, reason, size_bytes, content_withheld}` for every artifact that was not written
verbatim:
- `status` is one of `fields_withheld`, `content_withheld`, `write_failed`;
- `reason` is one of `content_withheld:secret_policy`, `artifact_write_failed`,
  `artifact_serialization_failed`.

No hash of withheld content is computed, and neither the matched text nor any exception message
is ever stored. `final_state.json.final_diff_withheld` is a boolean.

Semantics:
- Withheld content changes neither outcome, validity nor eligibility.
- An evidence artifact that could not be stored (`write_failed`) makes a still-valid attempt
  `invalid:harness`, and therefore `not_countable:invalid`.
- If `result.json`/`manifest.json` themselves cannot be stored, `ArtifactFinalizationError` is
  raised; cleanup has already run.
- `result.audit_run_directory(run_dir)` is the canonical per-attempt check.

### Reporting units (G3)

Reports keep these counts apart and never merge them:
- **planned cells** (task × configuration × repetition);
- **attempts** (one `run_id` each, all kept);
- **countable observations** (`countable`, at most one per cell);
- **external interruptions** (`not_countable:external_interruption`);
- **invalid attempts** (`not_countable:invalid`, by `run_validity`).

A replacement attempt under a predeclared rule is another attempt for the same cell, never an
additional observation. More attempts than planned cells is therefore possible. How attempts
are linked is decided by G10. Final statistical analysis is not defined here.

A legitimate task failure (`agent_outcome=completed`, `acceptance=fail`) is a **valid** run.
Only infrastructure/protocol problems make a run invalid (protocol §10). Agent integrity
violations are *outcomes* (valid, not resolved), not invalid runs (F13).

### Timeout semantics (G1, 2026-09-27)

The wall-clock cap is enforced by `process_control.run_with_deadline`. The agent process runs in
its own session. On expiry the harness terminates everything the run owns: the process group,
plus every descendant tracked through `/proc` by `(pid, starttime)`. This second part is needed
because `bwrap --new-session` moves the inner tree into another group. Nothing is ever selected by
process name.

- **Cap reached, tree terminated** → `agent_outcome=timeout`, `run_validity=valid`,
  `interruption_reason` set, `agent_exit_code=null` (a harness-terminated process has no exit code
  of its own; none is fabricated). Output emitted before the cap is kept, and the final state is
  evaluated. No automatic retry.
- **Termination not confirmed** (survivor, signal error, pipes still held, no `/proc`) →
  `agent_outcome=harness_error`, `run_validity=invalid:harness`, `harness_failure=true`, reason in
  `invalid_reason`.
- Termination metadata goes to the allowlisted artifact `process.json`: termination kind,
  signals sent, tracked PIDs, survivors, elapsed time, budget, and the raw return code. It is not
  referenced from `result.json`, so the schema is unchanged.
- If an auth or limit marker appears before the cap, the existing auth/limit classes keep their
  precedence (the G4 caveat applies).

### C2 runs and treatment provenance (G2/G9, 2026-09-27)

One C2 run = one `result.json` holding two CLI invocations. The existing fields represent it:

- `phase1_exit_code` / `phase2_exit_code` (the latter `null` if phase 2 never started);
- `agent_outcome` and `agent_exit_code` of the last executed invocation;
- `session_continuity_verified` is true only if both phases reported exactly the expected UUID;
- `c2_protocol` is `ok`, `phase1_write` or `phase_transition_failed`. Either violation →
  `run_validity=invalid:c2_protocol`, and the run is not evaluated.

No schema change was needed. Per-phase evidence goes to allowlisted artifacts:

- `phase1.*` and `phase2.*` (`stdout.txt`, `stderr.txt`, `events.jsonl`, `process.json`);
- `plan.txt`, the phase-1 `result` text if emitted;
- `c2.json`: per-phase envelope/session flag/budget/timing/outcome, the phase-1 read-only check,
  and the inter-phase gap.

`result.artifacts` points to the last executed phase. (Superseded by the G5/G6/G7 note below
for `treatment.json` and `changed_files.json`.) Every configuration writes
`treatment.json`: expected hashes (from the manifest), initial and final root instruction-file
hashes, and `modified_by_agent`. `changed_files.json` is computed against pristine + expected
treatment.

### Baseline, agent state, diff, evaluator, treatment drift (G5/G6/G7, 2026-09-27)

- `baseline.json`: pristine fixture name, expected and observed neutral commit, fixed metadata.
- `start_state.json`: the **agent-visible start state** (pristine + seeds + treatment), with its
  tree hash and per-file hashes. It is distinct from the neutral pristine baseline.
- `final_state.json`: final tree hash and files, `start_tree_hash`, `baseline_commit`,
  `head_commit`, `head_moved`, `final_diff_withheld`.
- `changed_files.json`: now relative to the agent start state
  (`added`/`modified`/`deleted`/`renamed`); `final.diff` is the matching patch, referenced by
  `result.artifacts.final_diff`. Only `.git`, `__pycache__` and `.pytest_cache` are excluded.
- `treatment.json`: `expected_start`, `start` and `final` instruction state, `ok`, `violations`.
- `evaluator.json`: axes plus per-check `kind`/`status`/`exit_code`/output tails, the
  protected-path `restoration` record, and `injected` hidden file names (never their content).
- `evaluator.json.sandbox` (G5s, 2026-09-28): evaluator-sandbox provenance: `kind` (`srt`),
  `version` (`g5s-v2` since G8; was `g5s-v1`), `policy_hash`, `identity` (roles, task layout paths, pinned toolchain;
  the credential path only as `credential_path_sha256`) and `production_safe`. No secret values
  and no configuration: the hash is identical for C0/C1/C2 of a task. An evaluator-sandbox failure
  sets `evaluator_error=true` with every check `error`. See `docs/G5S_EVALUATOR_SANDBOX.md`.
- New `run_validity` value **`invalid:treatment_drift`**. It is additive, so records written
  before it still validate; per the versioning rule it stays within `run-result/v0`.

### Instruction loader and protected `.claude` (G11, 2026-09-27)

`settings_policy_hash` (the envelope hash) now covers `instruction_loader = "add_dir_claude_md"`.
Every invocation of every configuration runs with `--setting-sources ""`, `--add-dir <wc>` and
`CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`. `security_policy_hash` now covers
`protected_wc_subpaths = [".claude"]`, which is write-protected in every phase. Runtime seeding
now includes the empty directories `.claude/commands/` and `.claude/agents/`. Evidence and status:
`docs/G11_TREATMENT_LOAD_SMOKE.md`.

### No token/cost metrics yet

No usage/token/cost field is part of the required result schema (protocol §7 / O8). When the CLI
output is inspected across pilot runs, the fields that are actually present and stable will be
recorded separately with their exact emitted names; until then they are omitted, not estimated.

## Security-sensitive exclusions

Neither record contains a secret. Guaranteed by construction and tested
(`test_artifacts_secrets.py`):

- the schemas declare **no** credential/token/secret/password/oauth/api-key field
  (`workspace_token` and `session_id` are non-secret opaque ids, explicitly allowed);
- artifacts are written through an allowlist and a secret scanner that refuses content bearing
  `sk-ant-`, a `.credentials.json` path, or a fake canary marker;
- the credential file is never copied; the real credential path appears only as a protected
  pathname inside the security policy, never as content.

## Schema versioning rule

`schema_version` / `result_schema_version` are `run-manifest/v0` and `run-result/v0`. Any
**backward-incompatible** change to a record's shape (removing/renaming a field, tightening a
type, changing a conditional rule) increments the version (`…/v1`) and is accompanied by a
protocol amendment; records written under different schema versions are not pooled. Additive,
backward-compatible fields may be introduced within `v0` only if older records still validate.
