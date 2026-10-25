# CodeAgent ConfigLab — Study 01 Gate 5: Operator Freeze Decisions

Status: **Gate 5 closed: operator values recorded 2026-10-25.** This is the operator's
closure of every open decision in `docs/STUDY_01_PROTOCOL.md` §6.2 (S1–S11, C-a, C-b, C-c). It is
**not** the Gate-6 immutable snapshot:

- no FINAL cell has been executed;
- the final 54-entry schedule has **not** been generated;
- `study_snapshot_hash` and `study_freeze_commit` do **not** exist yet.

Gate 6 (`STUDY_01_PROTOCOL.md` §7, §10) writes the freeze material from these values, generates the
schedule from the frozen seed and computes `study_snapshot_hash`. Until then, these values are not
covered by any snapshot hash.

Sources:
- the read-only Gate-5A audit (2026-10-25), with every identity below recomputed from repository
  bytes or read from the stored evidence;
- the Gate-3 re-check record, `docs/STUDY_01_GATE3_RECHECK.md`.

Basis tags:
- **[OPERATOR]** new operator choice at Gate 5;
- **[G4]** operator-approved Gate-4 fact;
- **[INHERITED]** already frozen by protocol or pilot documents;
- **[OBSERVED]** current repository observation.

## Decision summary

| ID | Frozen operator value | Basis |
|---|---|---|
| S1 | The six FINAL packages below, by `task_version_hash` | [G4] + [OBSERVED] recomputed |
| S2 | Per-task source scopes + metric rules 1–3 below | [G4] scopes + [OPERATOR] rules |
| S3 | Exact byte-for-byte reuse of the `pilot-v1` treatments; one common `CLAUDE.md` | [OPERATOR] + [INHERITED] bytes |
| S4 | Requested model `claude-sonnet-5` | [OPERATOR] + [INHERITED] pilot value |
| S5 | Effort `high` | [OPERATOR] + [INHERITED] pilot value |
| S6 | Timeout `900` s; C2 one shared deadline across phase 1 + phase 2 | [OPERATOR] + [INHERITED] F5 |
| S7 | `harness_git_sha = c9e2e32c030d129e9cef53dca5c7e3b539c675f6` | [OPERATOR] + [OBSERVED] Gate 3 |
| S8 | Evaluator identity + `g5s-v2` + `harness_git_sha` (semantic rule below) | [OPERATOR] |
| S9 | Seed `configlab-study01-v1-order`; `no_same_task_consecutively = false`; implemented algorithm unchanged | [OPERATOR] |
| S10 | Token / usage: **EXCLUDED FROM FORMAL STUDY-01 METRICS** | [OPERATOR] |
| S11 | Unnecessary-change rubric: **EXCLUDED FROM FORMAL STUDY-01 METRICS** | [OPERATOR] |
| C-a | Pilot-validated replacement / re-evaluation policy, unchanged, plus the ordering clarification | [OPERATOR] + [INHERITED] |
| C-b | Agent-time field binding below | [OPERATOR] + [INHERITED] semantics |
| C-c | `STUDY_01_PROTOCOL.md` §8 adopted unchanged | [OPERATOR] |

## S1 — six FINAL task packages

Package directories: `fixtures/final/<task_id>/`. Every `task_version_hash` was recomputed with
`TaskPackage.version_hash()` and equals the recorded gate hash. `TaskPackage.gate_errors()` is
empty for all six.

PASS evidence lives in the gate results store (`PILOT_TASK_STANDARD.md` §11.3) under
`/home/cclab/cclab-final-gate/results/gate/`. Every listed file has `status: PASS`,
`problems: []` and `model_calls: 0`.

| Task | `task_version_hash` | PASS evidence (`generated_at`) | Evidence file SHA-256 |
|---|---|---|---|
| F-PY-BUG-01 | `a918f37f7837555cc177c9d5b02449c32e44519970f91c587e49d76875e1b939` | `F-PY-BUG-01/20261013T171817Z.json` | `7f3a71c764d08f603442f51739cfad6548a12b922ea98f291145feb7c670e4fb` |
| F-PY-FEAT-01 | `143e845b90c467ba607bc4b1afde4c1203319e35e8e17aaba173884bec61bda4` | `F-PY-FEAT-01/20261013T175813Z.json` | `50923f60453cba4371c202abab282f635197166090b71460d89c72ea97f95857` |
| F-PY-REF-01 | `4a8c4a6199b33dcc94a13117a12d2dc1e0f7eff1f2481a66abfc7b3b2d698484` | `F-PY-REF-01/20261013T182555Z.json` | `8e7aa560955eadf0faef051495ac86f718aa5337bfd7527e41a844c85295a6dd` |
| F-TS-BUG-01 | `58954b7dde81d5ac43a15bd2af320fc0a90677ac54e201804b4d69bc257913df` | `F-TS-BUG-01/20261023T154247Z.json` | `04c74688eb733789fc8ae0ff76364b99110bfc856beb912f83189a53b07a743c` |
| F-TS-FEAT-01 | `ada5d35aea5470491054424a2c8becdde46a14fb406bfd7bd1d99b8a8ede90fb` | `F-TS-FEAT-01/20261023T161302Z.json` | `26f4420dd453b86dd0718c8181e0df8ee82eee4724808e459e2374d5dba0b928` |
| F-TS-REF-01 | `a116478aa259d9bbb20c62631e9ad0a76a543d2b4c95e096c35f37925ff730ee` | `F-TS-REF-01/20261023T171829Z.json` | `5d34264970ff36c8ae16a54844896991c3647386b02e96483b9e82559eff5af7` |

## S2 — source scopes and metric rules

| Task | Source scope | Explicitly outside scope |
|---|---|---|
| F-PY-BUG-01 | `msgheaders/**` | Python list below |
| F-PY-FEAT-01 | `eventlog/**` | Python list below |
| F-PY-REF-01 | `svcconfig/**` | Python list below |
| F-TS-BUG-01 | `src/**` | TypeScript list below |
| F-TS-FEAT-01 | `src/**` | TypeScript list below |
| F-TS-REF-01 | `src/**` | TypeScript list below |

A path counts only if it matches the scope and is not excluded:

- **Python:** `tests/**`, `_hidden_tests/**`, `README.md`, `CLAUDE.md`, `.claude/**`,
  `**/__pycache__/**`, `.pytest_cache/**`, and every path outside the scope directory.
- **TypeScript:** `test/**`, `_hidden_tests/**`, `dist/**`, `*.tsbuildinfo`, `node_modules/**`,
  `package.json`, `package-lock.json`, `tsconfig.json`, `README.md`, `CLAUDE.md`, `.claude/**`, and
  every path outside `src/`.

Rules [OPERATOR]:

1. **Renames.** A rename counts as a changed source file when either the old path or the new path
   is inside the scope.
2. **Line delta that is not available.** A diff entry may be missing its textual line delta: the
   whole `final.diff` is withheld, or an entry is marked `# binary or oversized file; not inlined`
   / `# start content unavailable; not inlined`.
   - The file still counts as changed when it is inside the scope.
   - Its line delta is recorded as `unknown` / `withheld`, never 0.
   - If `changed_files.json` path names were withheld (`fields_withheld`), scope membership is
     recorded as unknown.
3. **No quality claim.** These rules do not make diff size a quality metric. Changed-file count and
   diff size are descriptive only.

The rules are applied at analysis time to the existing artifacts:
- `changed_files.json` (`added` / `modified` / `deleted` / `renamed`);
- `final.diff`;
- `final_state.json.final_diff_withheld`;
- `artifact_report.json`.

The existing artifacts already represent every distinction, so no harness change is involved.

## S3 — treatments

Exact byte-for-byte reuse of the frozen `pilot-v1` material (`treatments/pilot-v1/FREEZE.json`).
- One common `CLAUDE.md` serves all six tasks and both languages; this is the pilot-v1 policy and
  answers O14.
- Encoding of all three files: UTF-8 (ASCII content), no BOM, LF only, exactly one trailing
  newline.
- No treatment tuning.

| Role | Path | Bytes | SHA-256 |
|---|---|---|---|
| `CLAUDE.md` (C1, C2) | `treatments/pilot-v1/claude_md.md` | 612 | `213df66805a816a4dea6998580fd85c91c3d3a1beb08acb3dbdf7ddc000e0541` |
| C2 planning wrapper | `treatments/pilot-v1/planning_wrapper.txt` | 595 | `299b08446b440345a7f177258208c3bf8b1d33addc3934ed1356bb72a0c47fc4` |
| C2 approval message | `treatments/pilot-v1/approval_message.txt` | 101 | `dbf445a514ca2ae9576935d09d7add9cf9157f88ca01ae1388d65a1f1009ee14` |

## S4 / S5 / S6 — model, effort, timeout

- **S4:** `model_request = "claude-sonnet-5"`. This is the **requested** model identity. The model
  actually used is checked separately at execution time (`process.json.observed_model`, per C2
  phase). A mismatch fails closed as `invalid:harness`. There is no silent fallback.
- **S5:** `effort_request = "high"`, sent explicitly on every invocation.
- **S6:** `timeout_seconds = 900`.
  - C0/C1: one 900 s deadline.
  - C2: one shared 900 s deadline across phase 1 + phase 2. Phase 2 gets the remainder, not
    900 s per phase. The inter-phase gap is not charged.

The harness at S7 accepts all three values without code changes.

## S7 — `harness_git_sha`

`c9e2e32c030d129e9cef53dca5c7e3b539c675f6` is the validated harness implementation identity: Gate 3
passed, and the re-check is in `docs/STUDY_01_GATE3_RECHECK.md`.

- It remains the Study-01 `harness_git_sha` even after later commits add task fixtures,
  documentation or freeze material that do not change harness behavior.
- A later repository HEAD is never substituted for it.
- Any harness change creates a new `harness_git_sha`, and therefore a different study snapshot
  (`STUDY_01_PROTOCOL.md` §7.3).

## S8 — task and evaluator identities

**Binding semantic rule [OPERATOR]:** the snapshot identity of a task's evaluator is
`evaluator_identity` + evaluator-sandbox semantic version `g5s-v2` + `harness_git_sha`.

- `evaluator_identity` (`TaskPackage.evaluator_identity()`) pins the task's evaluator
  specification: checks, protected paths, environment, `generated_outputs` and the sandbox
  version.
- `g5s-v2` names the semantic sandbox-policy contract.
- `harness_git_sha` pins the code that renders and enforces that contract.

The runtime sandbox `policy_hash` (`evaluator.json.sandbox.policy_hash`) includes absolute
filesystem paths, so it differs between environments. It is kept as execution and evidence
provenance only. It is **not** a portable snapshot identity. No new sandbox policy or evaluator is
introduced.

| Task | `task_version_hash` | `evaluator_identity` | Structural check (SHA-256) | Language / toolchain |
|---|---|---|---|---|
| F-PY-BUG-01 | `a918f37f7837555cc177c9d5b02449c32e44519970f91c587e49d76875e1b939` | `0b39f016ee2238cc3aa9f3fd4b940ae769bdee21c5ffffab2b93c9cf8e71f1fb` | — | Python; `/usr/bin/python3`; stdlib only |
| F-PY-FEAT-01 | `143e845b90c467ba607bc4b1afde4c1203319e35e8e17aaba173884bec61bda4` | `0fd724ef6339b60d4a0274a529f69128dcf1be443d7ade578c9a51afcf6de386` | — | Python; `/usr/bin/python3`; stdlib only |
| F-PY-REF-01 | `4a8c4a6199b33dcc94a13117a12d2dc1e0f7eff1f2481a66abfc7b3b2d698484` | `bea3716db9f8c6f66b7bf078b6ee272886e4d7752cd14b6f3b3e88ac1edd8557` | `hidden/structure_check.py` `242d2aad23953cce659ed36456b9c628a10e018ccbfea54cfa6b8a250804d7ed` | Python; `/usr/bin/python3`; stdlib only |
| F-TS-BUG-01 | `58954b7dde81d5ac43a15bd2af320fc0a90677ac54e201804b4d69bc257913df` | `d04566c439bd662b863ea341682c40545ecf3dee45f5fd4857fe5bddf6ad469a` | — | node 22.23.2; TypeScript 5.9.3; lockfile `3f0f6ad7606fe68431776443ebc79b481a54e8845458a46c76e9c6a5ef2a7689` |
| F-TS-FEAT-01 | `ada5d35aea5470491054424a2c8becdde46a14fb406bfd7bd1d99b8a8ede90fb` | `32d218ae949fd221809ba3e4a308be8e0e4b563bba7d14763d1b310c3213afea` | — | node 22.23.2; TypeScript 5.9.3; lockfile `4741697f8395628b2f5a05b664fb07d7d84500e6d3ccd73ff3e68ed11bb7dff8` |
| F-TS-REF-01 | `a116478aa259d9bbb20c62631e9ad0a76a543d2b4c95e096c35f37925ff730ee` | `039c9ad68a24240c0b52de6fdad994a1a79f911e7a3df7d4f0adbf161f395357` | `hidden/structure_check.cjs` `750b768fb5539abf14c0f5fb671d9294cbbcaa38f0a8ef1e6244aba7dfb1a4ad` | node 22.23.2; TypeScript 5.9.3; lockfile `26d2a619f940960be2e58e9f130d6a7448b95a8da71c50371c6252f1b96f5662` |

Notes:
- The structural checks live in each package's hidden tree, so `task_version_hash` already covers
  them. They are listed explicitly for readability.
- The vendored `node_modules/typescript` tree hash is
  `68a454533d107d0a11bb8a0ee25b8e31420166f294da8e7f2261cd9b15fc3bb3` for all three TypeScript
  tasks.

### Proposed Gate-6 serialization (proposal only; Gate 6 decides the format)

```json
{
  "harness_git_sha": "c9e2e32c030d129e9cef53dca5c7e3b539c675f6",
  "evaluator_sandbox_version": "g5s-v2",
  "toolchain": {"claude_code": "2.1.263", "node": "22.23.2", "npm": "10.9.8",
                "sandbox_runtime": "0.0.77"},
  "tasks": [
    {"task_id": "F-PY-REF-01",
     "task_version_hash": "4a8c4a6199b33dcc94a13117a12d2dc1e0f7eff1f2481a66abfc7b3b2d698484",
     "evaluator_identity": "bea3716db9f8c6f66b7bf078b6ee272886e4d7752cd14b6f3b3e88ac1edd8557",
     "statement_hash": "859e6705415961b5e1711ed52e93bcbb61ec153d07e0bdcc5af7c3da7d2f6269",
     "language": "python", "generated_outputs": [], "source_scope": ["svcconfig/**"],
     "structural_check_sha256": "242d2aad23953cce659ed36456b9c628a10e018ccbfea54cfa6b8a250804d7ed",
     "toolchain": {"python_binary": "/usr/bin/python3", "dependencies": "stdlib"}}
  ]
}
```

The example shows one of the six tasks; the other five follow the same shape with the values in
the S8 table. The fields fall into two groups:

- **Stable snapshot fields:** everything in the JSON above. The global part is in the series spec
  `toolchain` (`series.build_spec`) and is pinned by `harness_git_sha`.
- **Runtime / path-bound evidence (provenance only, never a snapshot key):**
  - per-attempt `evaluator.json.sandbox.policy_hash` and `.identity`;
  - the gate-environment `policy_hash` values in the PASS evidence;
  - absolute paths (`evidence_ref`, `node_binary`, `typescript_install_source`);
  - the observed Python interpreter version (3.14.4 on 2026-10-25).

The statement hashes of the other five tasks are:
- F-PY-BUG-01 `fdff9031aac4f023eb9ac40e4d32c57cef510f80798ac60baeded7956657652b`;
- F-PY-FEAT-01 `bc4a3abec944055c7787e4b3012daf44813350541cd8dc46b38562af84735def`;
- F-TS-BUG-01 `4bcad3637bdf89c2f19a2e7445b8f89bb89684b83b4afefa4542b9d5866d9794`;
- F-TS-FEAT-01 `a768c2296fb1b409ffd718e6a30e741fd13d2aa6ac340ec433a130d5600108fc`;
- F-TS-REF-01 `0d8a925f2d58ebe2a4c20c532cee4afc7f6b6bb336305325efb9720967cda6d8`.

## S9 — seed and run order

- `order_seed_text = "configlab-study01-v1-order"`, chosen before any FINAL outcome. Alternative
  seeds were not tried.
- `no_same_task_consecutively = false`, deliberately. No new scheduling constraint is added.
- **Algorithm:** the validated Gate-2 / Gate-3 FINAL implementation is used unchanged
  (`series._final_schedule` at S7):
  1. The canonical list is `[(task_id, cfg) for task_id in sorted(task_ids) for cfg in (C0, C1, C2)]`.
  2. For each block r = 1..3, `block_seed_r = int(sha256(f"{seed}#block-{r}")[:8], 16)`.
  3. The block order is `random.Random(block_seed_r).shuffle` of a fresh copy of the canonical
     list.
  4. Blocks run in order 1 → 3, and positions 1..54 are global.
- The 54-entry schedule is generated only at Gate 6, from these frozen inputs.

## S10 / S11 — exclusions

- **S10, token / usage:** EXCLUDED FROM FORMAL STUDY-01 METRICS.
  - O8 (whether a resumed C2 invocation reports per-invocation or cumulative usage) has never been
    verified.
  - Raw usage fields and events stay preserved where present.
  - Missing usage is never 0.
  - `total_cost_usd` under the Claude Pro setup is not a billed cost.
- **S11, unnecessary-change rubric:** EXCLUDED FROM FORMAL STUDY-01 METRICS.
  - No pre-specified frozen rubric exists.
  - Changed-file count and diff size stay descriptive metrics only.
  - No weighted or composite quality score is introduced.

## C-a — replacement / re-evaluation

The existing pilot-validated policy is adopted unchanged. Sources: `series.replacement_decision`,
`PILOT_SERIES_V0.md` "Replacement vs re-evaluation", `PILOT_PLAN.md` §10–§11 and
`STUDY_01_PROTOCOL.md` §6.3. This closes protocol O13 for FINAL runs.

| Attempt record | Handling |
|---|---|
| Countable result: completed, valid task failure (acceptance/regression `fail`), valid `timeout`, `error_exit` | The cell is complete. No replacement |
| `not_countable:evaluation_pending` | The evaluator re-runs on the preserved final working copy (tree hash verified). Never an agent rerun |
| `not_countable:external_interruption`, `invalid:infrastructure`, `invalid:harness`, `preflight_failed` | Replacement-eligible; operator approval required, never automatic |
| `invalid:fixture` | Eligible only with an operator note confirming the materialized copy (not the package) was corrupted |
| `invalid:leak`, `invalid:carryover`, `invalid:c2_protocol` + `phase1_write` | Series halt; hard stop, never resumable |
| Real cleanup failure | Recoverable halt: remediation, then explicit resume |
| Anything else (e.g. `invalid:treatment_drift`, `phase_transition_failed`) | Not eligible. The cell ends as `no_valid_attempt` |

Further rules:
- At most one replacement per cell.
- No outcome-quality reruns: no decision looks at evaluator verdicts.
- Every attempt is preserved.
- A replacement never increases the planned N.

**Operator clarification:** approved replacement attempts run only after all 54 planned original
cells have been attempted. They follow the deterministic order the series machinery already uses
(`Series._next`: every pending original in schedule order first, then `replacement_approved`
cells in schedule order). They do **not** run at the end of the current block.

## C-b — agent-time field binding

Paths are relative to the attempt directory and were verified against `process_control.py`,
`orchestration.py`, `lifecycle.py` and the pilot-v1 artifacts.

| Quantity | Exact source |
|---|---|
| C0/C1 agent time | `process.json` → `elapsed_seconds` |
| C2 phase-1 agent time | `c2.json` → `phases[label == "phase1"].process.elapsed_seconds` (= `phase1.process.json` → `elapsed_seconds`) |
| C2 phase-2 agent time | `c2.json` → `phases[label == "phase2"].process.elapsed_seconds` (= `phase2.process.json` → `elapsed_seconds`); if phase 2 never started (`c2.json.invocations == 1`), reported as not started, never 0 |
| C2 total agent time | phase-1 + phase-2 agent time (phase 1 alone when phase 2 did not start) |
| Excluded | `c2.json.inter_phase_gap_seconds`; evaluator, cleanup and lifecycle time |
| Not a performance metric | `result.json` → `duration_seconds` (whole lifecycle); `c2.json` → `phases[].duration_seconds` (orchestration wrapper) |
| Timeout | `result.json` → `agent_outcome == "timeout"` with `run_validity == "valid"` and `interruption_reason`. Process level: `timed_out: true`, `termination: "timeout_terminated"`, `deadline_budget_seconds` (900; C2 phase 2 receives the remainder of the shared deadline). If the C2 budget is exhausted at the end of phase 1, the result is `agent_outcome == "timeout"` with no phase-2 entry |

Notes:
- `elapsed_seconds` includes the harness's process-tree termination at a timeout, so it can
  slightly exceed 900. It is reported as measured, and timeouts are identified by the outcome
  fields.
- A missing process record is reported as missing, never 0.

## C-c — results presentation

`STUDY_01_PROTOCOL.md` §8 is adopted unchanged:

- task-by-task results first, with a planned-cell denominator:
  `R resolved · F failed · M no countable observation / N planned`;
- separate accounting of attempts, replacements and non-countable attempts by class;
- 18 planned cells per configuration and 54 overall;
- primary contrasts RQ1 = C1 − C0 and RQ2 = C2 − C1; C2 − C0 only as a labelled descriptive row;
- agent time shown over all countable attempts, with success, failure and timeout visible;
- C2 shown as phase 1 + phase 2 and as a total;
- source-scoped changed files and diff size, descriptive only;
- no weighted composite score;
- no significance or generalization claim that the six-task design cannot support.

## Remaining before Gate 6

1. Commit the six FINAL package directories (`fixtures/final/F-*/`; the review `F-*.zip` copies are
   byte-identical duplicates and are not part of any identity) and this record. This is operator
   approved and does not change S7.
2. Gate 6:
   - write the freeze material covering `STUDY_01_PROTOCOL.md` §7.2 from the values above;
   - generate the 54-entry schedule from the S9 seed;
   - compute `study_snapshot_hash`;
   - commit;
   - record `study_freeze_commit` externally.
