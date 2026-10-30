# CodeAgent ConfigLab

CodeAgent ConfigLab is a benchmark harness for comparing how a coding agent performs under
different repository-instruction and workflow configurations. It runs a real coding agent against
real task fixtures inside a controlled, deterministic, auditable series driver — not a mock or a
simulation.

**V1 scope.** V1 consists of the working evaluation harness plus the completed production pilot.
The final six-task / 54-run comparative benchmark (Study-01) has since been run and analyzed; see
[Study-01 Results](#study-01-results) below and `docs/study01/STUDY_01_RESULTS.md` for the full report.

## What's being compared: C0 / C1 / C2

Three configurations, differing only in the instruction material the agent receives (full
definitions in `docs/EXPERIMENT_PROTOCOL_V0.md` §3.2):

- **C0 — baseline.** No `CLAUDE.md`, `CLAUDE.local.md`, `.claude/` instruction content, or
  equivalent. The agent receives only the task statement.
- **C1 — repository instructions.** C0 plus exactly one frozen, version-controlled `CLAUDE.md` at
  the working-copy root, present from the first moment of the run.
- **C2 — explicit planning workflow.** C1 (the same `CLAUDE.md`) plus a two-phase run in one
  session: a read-only planning phase (the task statement embedded in a fixed planning wrapper),
  then a fixed, pre-written approval message that continues the *same* session into implementation
  with C0/C1's permissions.

The planning wrapper and approval message are part of the C2 treatment, not an incidental prompt
difference — the task statement itself is byte-identical across all three configurations, and
nothing else is allowed to differ.

## What the pilot established

A full pilot run (two task packages — one Python, one TypeScript — across all three
configurations, six planned cells plus one operator-approved replacement) exercised the entire
harness end to end against a real agent: deterministic scheduling, treatment isolation, the C2
two-phase protocol (including its shared wall-clock deadline and same-session continuation), model
provenance verification, evaluator/cleanup isolation, and the replacement/recovery policy. Two
concrete production defects were found and fixed during the pilot (production cleanup wiring, and
resume semantics for a recoverable halt) — both are documented, with the fix validated by
subsequent real attempts.

**The pilot validates the harness's machinery and protocol. It is not a comparison of C0, C1, or
C2 effectiveness** — two tasks, one repetition each, is not a statistically meaningful result, and
none is claimed. See `docs/PILOT_V1_CLOSEOUT.md` for the full closeout record.

## Study-01 Results

Study-01 ran six fixed coding tasks three times each under C0/C1/C2 and compared them with
matched, task-aware statistics. Full report: `docs/study01/STUDY_01_RESULTS.md`. Machine-readable
results: `docs/STUDY_01_RESULTS.json`. Public data tables: `docs/study01_data/`. Protocol:
`docs/STUDY_01_PROTOCOL.md`. Of the 54 planned cells, one original attempt was infrastructure-
invalid (an auth failure, not a task outcome) and was re-run once under the frozen replacement
policy — the study remains 54 planned cells, not 55.

| Comparison | Matched success change (frozen primary result) | Timing |
|---|---|---|
| RQ1: C1 vs. C0 | 16/18 → 16/18 resolved, 0.0 pp | C1 slower in 16/18 matched pairs; all 6 task-level medians slower |
| RQ2: C2 vs. C1 | 16/18 → 12/18 resolved, −22.2 pp | C2 slower in 18/18 matched pairs; 3 of 6 task-level successes worsened, none improved |

A verified post-hoc check found that most of the RQ2 gap traces to one component of the
composite success definition — an integrity (protected-path) check that was applied consistently
but was not disclosed to the candidate — rather than to functional (acceptance/regression)
failure; functional-pass rates were far closer across configurations (C0 16/18, C1 17/18, C2
16/18). The frozen result above is unchanged; see `docs/study01/STUDY_01_RESULTS.md` §8a for the full,
separately labeled sensitivity analysis.

**Scope:** the benchmark contains 54 cell observations but only six distinct task units; three
repetitions per task/configuration characterize within-task run variability, not 18 independent
samples. Tasks are synthetic, one per language × task-type combination, run under a single frozen
model/harness/environment. No significance testing was performed or is implied by these numbers.
Future studies can test task-set robustness and criterion-visibility fixes on new tasks.

## Where things stand

The **final benchmark** (Study-01) — a separate, larger task set producing a 54-cell dataset with
a comparative report across C0/C1/C2 — has been run and analyzed; see
[Study-01 Results](#study-01-results) above. The two pilot tasks were instruments only and are not
part of that final set.

- `docs/V1_STATUS.md` — what the harness currently provides, and what it doesn't yet contain.
- `docs/PILOT_V1_CLOSEOUT.md` — the pilot's scope, frozen execution identities, full execution
  history (including the historical Cell 1 replacement), infrastructure findings, and C2 protocol
  evidence.
- `docs/EXPERIMENT_PROTOCOL_V0.md` — the full experimental protocol (configurations, clean-run
  contract, C2 contract, etc.).
- `docs/PILOT_PLAN.md` / `docs/PILOT_SERIES_V0.md` — the pilot's binding plan and series-driver
  design.
- `docs/PILOT_TASK_STANDARD.md` / `docs/RUN_MANIFEST_V0.md` — task-package and run-manifest
  formats.

## Running the series driver

```
python -m codeagent_configlab series freeze  --config series.json --harness-root <dir>
python -m codeagent_configlab series status  --config series.json --harness-root <dir>
python -m codeagent_configlab series plan    --config series.json --harness-root <dir>
python -m codeagent_configlab series run-next --execute --config series.json --harness-root <dir>
```

`run-next --execute` is the only command that makes a real model call; every other action
(`freeze`, `status`, `plan`, `approve-replacement`, `recover`, `reevaluate`, `remediate-cleanup`,
`resume`) is model-free. See `src/codeagent_configlab/__main__.py` for the full command reference.

## Reproducing: checkout requirements

The V1 benchmark environment is WSL/Linux. The frozen TypeScript fixture
(`fixtures/pilot/P-TS-01/pristine/node_modules/.bin/`) contains real symlinks, and they are part of
the frozen task bytes. A native Windows Git checkout with symlink support disabled
(`core.symlinks=false`, the usual default) writes them as plain files, which changes the frozen task
hash. Clone and run under WSL/Linux, or make sure Git preserves symlinks. A native Windows checkout
is not supported as byte-preserving. `.gitattributes` (`* -text`) turns off Git line-ending
conversion so that tracked files keep their exact bytes.

## Tests

```
PYTHONPATH=src:tests python -m pytest tests -q
```

Most test files also run under `python -m unittest` (stdlib-only, no `pytest` required) — see
individual test file docstrings.
