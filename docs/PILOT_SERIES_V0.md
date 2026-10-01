# Pilot series driver (G10, `pilot-series/v0`)

Status: implemented and verified model-free, 2026-09-28. No pilot cell has been run.
Code: `task_package.py`, `series.py`, `python -m codeagent_configlab series …`.

## Planned cell vs attempt

- A **planned cell** is one intended observation, `task × configuration × repetition`. `pilot-v1`
  has 2 × 3 × 1 = **6** cells. `cell_id = "cell-" + sha256(pilot_version, task_id,
  task_version_hash, configuration, repetition)[:16]`, derived from the frozen specification
  only.
- An **attempt** is one execution of the single-run lifecycle. Its `run_id` is the opaque
  attempt id.
  - Attempt 1 is the **original**. A **replacement** is attempt 2, the same cell (same
    `repetition`), never a new cell or repetition.
  - Linkage lives in the attempt manifest: `cell_id`, `attempt_ordinal`, `attempt_kind`,
    `original_attempt_id`, `predecessor_attempt_id`, `replacement_reason`.
- A **countable observation** is an attempt whose `analysis_eligibility` (G3/G8) is
  `countable`. A cell is complete with its first countable attempt. The "best" attempt is
  never chosen, and every attempt is kept.

## Replacement vs re-evaluation (PILOT_PLAN §10/§11)

The decision comes from `series.replacement_decision`, which uses only status axes and never
verdict quality:

| Attempt record | Decision |
|---|---|
| `countable` (incl. acceptance/regression fail, valid `timeout`, `error_exit`) | `complete`, no replacement |
| `not_countable:evaluation_pending` (G8) | `reevaluate`: evaluator re-run on the preserved final WC, no new agent attempt |
| `not_countable:external_interruption` (limit) | `eligible` |
| `invalid:infrastructure`, `invalid:harness`, `preflight_failed` | `eligible` |
| `invalid:fixture` | `eligible_operator_confirm` (an operator note is required) |
| `invalid:leak`, `invalid:carryover`, `invalid:c2_protocol`+`phase1_write` | `halt`: the series stops for review |
| anything else (e.g. `treatment_drift`, `phase_transition_failed`) | `not_eligible`, i.e. no valid attempt |

- Replacements are **never automatic**. `approve-replacement` records the operator decision, and
  at most **1** replacement is allowed per cell (frozen §11). If it is also non-countable, the
  cell ends as `no_valid_attempt`.
- Approved replacements run after the last planned original, in original schedule order.
- **Re-evaluation:**
  - it checks that the preserved WC (`runs/<workspace_token>`) still has the tree hash recorded
    in `final_state.json`;
  - it appends to `reevaluation.json` in the attempt dir; `result.json` and the agent evidence are
    never rewritten;
  - it logs a `reevaluated` event whose eligibility comes from the same canonical rule.

## Frozen specification and schedule

- `freeze` writes `spec.json` (`schemas/pilot-series-spec.schema.json`) and `schedule.json` once.
  The spec pins:
  - per-task version hash, gate status, statement hash and evaluator identity;
  - treatment hashes, model and timeout;
  - envelope/security policy hashes and the toolchain;
  - the replacement policy.
- **Every command rebuilds the spec from the config and packages. Any difference fails closed
  (`SeriesFrozenError`).** A replacement's frozen cell spec (the manifest minus attempt/runtime
  fields) must equal the original's.
- Real execution also requires `readiness_errors(spec) == []`:
  - a concrete `model_request`;
  - a concrete `effort_request`;
  - a numeric `timeout_seconds`;
  - a frozen CLAUDE.md, wrapper and approval message;
  - every package gate `PASS` for exactly its current bytes;
  - evaluator identity;
  - one repetition.
- **Schedule:** exactly PILOT_PLAN §6.
  1. `seed = int(sha256(order_seed_text)[:8], 16)`;
  2. `first = rng.choice(tasks)`; tasks alternate from there;
  3. each task's configuration order is a `rng.shuffle` of `[C0, C1, C2]`, reshuffled until it
     differs from the previous task's;
  4. positions are `t1·c1, t2·c1, t1·c2, t2·c2, t1·c3, t2·c3`.

  Interpretation: each shuffle starts from the canonical list. The schedule is generated at
  freeze, is independent of outcomes, and is regenerated and compared on every resume.

## Manifest is the executable truth

- The attempt manifest carries the frozen `model_request`, `effort_request` and `timeout_seconds`.
- `RunLifecycle.execute` refuses a `budget_seconds` differing from a numeric manifest timeout,
  and a runner whose `model` or `effort` differs from the manifest. The driver never passes a
  budget. Both C2 phases run through the same `RealAgentRunner` instance, so model/effort cannot
  diverge between phase 1 and phase 2.
- C0/C1 get one G1 `Deadline` of the manifest timeout; C2 shares one `Deadline` across both
  phases.

## State, resume, crash

- `events.jsonl` (append + fsync, `schemas/pilot-series-event.schema.json`) is the only state. It
  holds `attempt_started`, `attempt_finished`, `attempt_aborted`, `replacement_approved`,
  `reevaluated` and `series_halted`.
- Cell states (`pending`, `observed`, `evaluation_pending`, `replacement_eligible`,
  `replacement_approved`, `no_valid_attempt`, `halted`, `ambiguous`) are derived from events.
- Resume means reading the events and continuing at the next `pending` position.
- A `started` event without a matching end is `ambiguous`; execution and planning refuse until
  `recover`:
  - if `result.json` exists and passes `audit_run_directory` → `attempt_finished` (recovered);
  - otherwise → `attempt_aborted` = `invalid:harness`, non-countable and replacement-eligible.

  An attempt id is never executed twice. A lifecycle exception inside the driver is recorded as
  `attempt_aborted` and re-raised.

## Namespaces

- Series metadata lives under `<harness_root>/series/<pilot_version>/`: spec, schedule, events,
  and `attempts/<run_id>/` (the per-attempt results). The harness root is `denyRead` in every
  agent sandbox.
- WCs stay `runs/<opaque workspace_token>`; no series, cell or task metadata goes into them.
- Manifests carry `namespace`: `PILOT`, `HARNESS_SMOKE_ONLY` or `FINAL`.
  - `load_pilot_attempt` refuses anything without `namespace=PILOT` and a `cell_id` (e.g. smoke).
  - `assert_promotable_to_final` refuses every pilot attempt.
  - The driver refuses a non-PILOT spec.

## Task packages

`TaskPackage` (`package.json` under the harness root) exposes the statement, pristine, hidden,
reference and evaluator configuration, following PILOT_TASK_STANDARD §2/§13. The version hash
covers the statement, pristine tree (incl. `node_modules`), hidden tree, evaluator configuration
and reference tree. A package whose recorded gate is not `PASS` for exactly these bytes is refused.
The gate itself (§11) is run by the author, not by this driver. The package's `generated_outputs` (task standard §13a) is part of its version and
flows unchanged into every attempt's lifecycle and into re-evaluation's tree check.

## CLI

`python -m codeagent_configlab series {freeze|status|plan|approve-replacement|recover|reevaluate|run-next} --config <json> --harness-root <dir>`.

- `plan` is the dry run: safe metadata only, nothing created.
- `run-next` needs `--execute`, refuses unless ready, and runs **one** attempt with a
  `RealAgentRunner` built from the manifest and the production evaluator sandbox.

## Not implemented / operator items

- The PILOT_PLAN §3 **E3 contingency** (one extra C2 run on P-PY-01 if neither C2 run reaches
  phase 2) is **not** a replacement. It is not automated. `attempt_finished.c2_phase2_reached`
  records the evidence needed to decide it.
- Model, timeout, the CLAUDE.md text, wrapper and approval, the task packages with their gates,
  and the order seed text (default `configlab-pilot-v1-order`) are operator inputs.
