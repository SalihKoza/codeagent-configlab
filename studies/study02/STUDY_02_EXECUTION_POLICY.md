# Study-02 Execution Policy (FROZEN, Gate 7I)

## 1. Timing budget

900 seconds, shared. C1: one 900-second `Deadline` for the single candidate process. C2: one
shared 900-second `Deadline` across phase 1 + phase 2 — phase 2 receives whatever remains when
phase 1 ends; it never receives a fresh 900 seconds. No hidden extra time relative to C1's budget.
Excluded from timing: `c2.json.inter_phase_gap_seconds`, evaluator time, fixture setup/cleanup,
scheduling delay, `result.json.duration_seconds`.

## 2. Authentication / external-invalidity taxonomy

| Category | `AgentOutcome` / `RunValidity` | Classification |
|---|---|---|
| Authentication failure | `AUTH_FAILURE` → `invalid:infrastructure` | Non-countable, invalid |
| Subscription / usage limit | `LIMIT_INTERRUPTED`, `run_validity` stays `valid` | `not_countable:external_interruption` — non-countable but not invalid |
| Model unavailable | Halt condition if C1/C2 model-identity equality cannot be preserved | Execution halts for that cell rather than silently substituting a different model |
| Service outage | Unrecognized terminal API error → `ERROR_EXIT` reason `error_exit:api_error_unclassified:<code>/<status>` | Captured, never silently absorbed |
| Local sandbox/runtime failure | `preflight_failed` / evaluator-sandbox init failure | Evaluator-error/infrastructure category, never a task verdict |

All `AUTH_FAILURE` instances collapse into one bucket with no cause sub-classification
(expired/revoked/wrong-org) — accepted, not a blocker. No paid API fallback is introduced for any
row in this table.

## 3. Replacement policy

| Observed outcome | Policy |
|---|---|
| Countable result (incl. acceptance/regression fail, valid timeout, valid `error_exit`) | No replacement |
| `not_countable:evaluation_pending` | Evaluator re-evaluation on preserved working copy; never an agent rerun |
| `REPLACEMENT_ELIGIBLE_VALIDITY = (invalid:infrastructure, invalid:harness, preflight_failed)`, plus `limit_interrupted` | Operator-approved replacement only |
| `invalid:fixture` | A narrower category than the replacement-eligible list: flags a possible fixture-provenance problem for explicit operator **confirmation** before any further action, distinct from an automatic replacement-approval path |
| `HALT_VALIDITY = (invalid:leak, invalid:carryover)` | Halt and investigate |
| Any cell | Maximum one replacement (`max_replacements_per_cell = 1`, frozen default) |

The original attempt is always preserved. All 48 original attempts must be attempted before any
approved replacement executes. Replacement never changes the 48-cell experimental denominator; it
inherits the original's `cell_id`/`task_id`/`configuration`/`repetition`, plus provenance fields
(`attempt_ordinal=2`, `attempt_kind="replacement"`, `original_attempt_id`, `predecessor_attempt_id`,
`replacement_reason`). A replacement decision is outcome-quality-independent.

## 4. Model / effort

Requested model `claude-sonnet-5`, effort `high` — frozen into the spec via `SeriesConfig.model_request`/
`effort_request`, part of `spec_hash`.

## 5. Harness identity

`harness_git_sha`: `1f576bf245411b00cd7856ac835bd651fcd281d8` — contains both required harness
changes (explicit configuration-set support, commit `d263dc32904c171c5da74e8ed1cf084c7a705bfa`;
explicit task→treatment routing, commit `1f576bf245411b00cd7856ac835bd651fcd281d8` itself).
`study02_implementation_git_sha`: `bbf8bba2ee7ffdefaca392f5c50a7d4ae585590e` (task/treatment
content identity, kept distinct from execution harness identity).

## 6. Status

**FROZEN** at Gate 7I.
