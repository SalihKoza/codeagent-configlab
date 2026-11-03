# Study-02 Protocol (FROZEN, Gate 7I)

## 1. Research question

> Under an identical frozen repository `CLAUDE.md` for each task and fully candidate-visible task
> constraints, does the explicit two-phase plan-then-approve workflow (C2) change contract-compliant
> task completion relative to the same substantive `CLAUDE.md` without that workflow (C1) on a new
> set of 12 distinct coding tasks across six repository families?

C1 is not "no planning" — it still performs any planning the candidate chooses, unstructured. C2
measures the incremental, *tested* two-phase workflow, not Claude Code's built-in Plan Mode (a
different mechanism entirely, never invoked here).

## 2. Design

- 12 distinct coding tasks across 6 repository families (3 Python: `throttlekit`, `stocktrack`,
  `configmerge`; 3 TypeScript: `dedupe-cache`, `qs-normalize`, `mini-queue`). Each family
  contributes exactly 2 tasks. Each language's 3 families instantiate all three possible
  unordered task-category pairs exactly once (bug+refactor, bug+feature, feature+refactor) — a
  balanced 3×3 design, not an arbitrary split.
- Configurations: C1, C2 (no C0, no C3).
- Repetitions: 2.
- **48 planned experimental cells** (12 × 2 × 2): 24 C1, 24 C2; 24 cells per repetition block;
  every task×configuration pair exactly once per repetition.
- **48 planned cells does not necessarily imply 48 countable observations.** A non-countable
  attempt is never converted into a task failure; it is reported as `no_valid_attempt` for that
  cell if no countable attempt exists, and the cell stays in the planned-cell denominator (48),
  never imputed or silently dropped.

## 3. Primary independent unit

`task`. The 48 cells are not 48 independent samples — they are 12 nested, non-independent task
units, each observed twice per configuration. Repetition-family sharing (two tasks per family
receive byte-identical treatment) is a stated structural limitation, not an independence claim.
Repetition characterizes within-task execution variability, not an additional independent sample.
If anything, this design is less inferentially supportable than Study-01's 6-task/3-repetition
design — stated plainly in reporting, not papered over.

## 4. Primary endpoint: `resolved`

A selected (countable) observation is `resolved` only if: `run_validity == valid` **and**
`acceptance == pass` **and** `regression == pass` **and** `integrity == clean`. `resolved` is
evaluated only for an observation whose `analysis_eligibility.status == countable`. Run validity,
analysis eligibility, and task success (`resolved`) remain three separate questions, never merged
into one combined status. Every formal integrity/scope restriction that can affect this endpoint
is candidate-visible (no hidden success criterion).

## 5. Validity / eligibility / outcome-success (three-tier separation)

- **Run validity** (`RunValidity`): `valid`, `invalid:infrastructure`, `invalid:harness`,
  `invalid:fixture`, `invalid:leak`, `invalid:carryover`, `invalid:c2_protocol`,
  `invalid:treatment_drift`, `preflight_failed`. Answers "was the attempt executed as specified."
- **Analysis eligibility** (`AnalysisEligibility`): `countable`, `not_countable:external_interruption`,
  `not_countable:invalid`, `not_countable:evaluation_pending`. Derived automatically from
  `run_validity` + `AgentOutcome`, never set independently.
- **Task success** (`resolved`): computed only on countable observations, §4 above.

A candidate timeout under a functioning 900-second budget is `valid`, `countable`, and
unsuccessful — unless another independent validity problem exists.

## 6. Replacement policy

| Observed outcome | Policy |
|---|---|
| Countable result (incl. acceptance/regression fail, valid timeout, valid `error_exit`) | No replacement — cell complete as observed |
| `not_countable:evaluation_pending` | Evaluator re-evaluation on preserved final working copy; never an agent rerun |
| `REPLACEMENT_ELIGIBLE_VALIDITY = (invalid:infrastructure, invalid:harness, preflight_failed)`, plus `limit_interrupted` | Operator-approved replacement only, never automatic |
| `invalid:fixture` | Operator **confirmation** required before any further action — a distinct, narrower category from the replacement-eligible list above: it flags a possible fixture-provenance problem for explicit operator review, not an automatic replacement path |
| `HALT_VALIDITY = (invalid:leak, invalid:carryover)` | Halt and investigate; no plain replacement |
| Any cell | Maximum one replacement (`max_replacements_per_cell = 1`) |

The original attempt is always preserved (append-only event log). All 48 original attempts must be
attempted before any approved replacement executes. Replacement never changes the 48-cell
denominator; it inherits the original's `cell_id`, `task_id`, `configuration`, `repetition`. A
replacement decision is outcome-quality-independent. **Important reporting clarification**: if
both an original and its permitted replacement remain infrastructure-invalid, that planned cell
remains missing/non-countable — it is never converted to a candidate failure.

## 7. Timing

C1: candidate-process elapsed time, one 900-second deadline. C2: phase-1 elapsed + phase-2
elapsed, one shared 900-second deadline across both phases (phase-1 consumption reduces phase-2's
remaining budget; phase-2 never receives a fresh 900 seconds). Excluded from timing: operator
approval gap, inter-phase harness waiting, evaluator time, setup, cleanup, scheduling delay. No
hidden additional planning time for C2.

## 8. Model / effort

Requested model: `claude-sonnet-5`. Effort: `high`. Interpretation is based on contemporaneous
equality between C1 and C2 within Study-02 — this protocol does not claim backend identity with
Study-01 merely from the model alias being the same string.

## 9. Authentication / external invalidity

Authentication failure, subscription/usage limit, model unavailable, service outage, and local
sandbox/runtime infrastructure failure are none of them candidate task failures — each is either
`invalid:infrastructure`-class (non-countable, invalid) or, for subscription/usage limits,
`valid` but `not_countable:external_interruption`. No paid API fallback is introduced for any of
these categories. See `STUDY_02_EXECUTION_POLICY.md` for the full taxonomy table.

## 10. Study-03 firewall

Study-03 (a C3 intervention study) remains conditional and is not defined here. This protocol does
not require Study-03 to exist. An intervention study becomes justified only if Study-02 reveals a
workflow failure or tradeoff that is simultaneously reproducible (consistent across the task set),
treatment-associated (attributable to the C1/C2 contrast rather than task-specific noise),
actionable, and non-artifactual (not explainable by a disclosure gap, infrastructure issue, or
measurement confound). No C3 treatment, mechanism, or design decision is made or implied here.

## 11. Historical identities (unchanged, not rewritten by this protocol)

- Study-01 harness SHA: `c9e2e32c030d129e9cef53dca5c7e3b539c675f6`.
- Study-02 implementation commit: `bbf8bba2ee7ffdefaca392f5c50a7d4ae585590e`.
- Two-arm harness support commit: `d263dc32904c171c5da74e8ed1cf084c7a705bfa`.
- Final harness commit (treatment routing): `1f576bf245411b00cd7856ac835bd651fcd281d8`.

## 12. Status

**FROZEN** at Gate 7I. No Study-02 production candidate execution occurred before this freeze.
Production attempt count at freeze: 0. See `README.md` for the hash rule and identities table.
