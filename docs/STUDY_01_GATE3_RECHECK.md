# CodeAgent ConfigLab — Study 01 Gate 3 Re-check (persisted record)

Status: **re-check PASS, 2026-10-25.** This file persists the evidence that the Study-01 harness
candidate still passes the Gate-3 regression and backward-compatibility gate
(`STUDY_01_PROTOCOL.md` §10).

- The original Gate-3 validation ran on 2026-10-09 (report 2026-10-09T15:03Z, result
  "GATE 3 PASS — CANDIDATE HARNESS SHA VALIDATED"). Its result existed only in the operator
  session, not in the repository.
- This re-check repeats the original commands at the same commit and records what was observed.
- No model calls were made. Harness source was not modified. Python ran with
  `PYTHONDONTWRITEBYTECODE=1`, and pytest ran with its cache provider disabled.

| Item | Value |
|---|---|
| Validated harness candidate (`harness_git_sha`) | `c9e2e32c030d129e9cef53dca5c7e3b539c675f6` |
| HEAD at re-check (WSL Git) | `c9e2e32c030d129e9cef53dca5c7e3b539c675f6` |
| Tracked changes at re-check (WSL Git) | none: `git diff --stat HEAD` empty; only untracked `fixtures/final/` |
| Re-check window (UTC) | 2026-10-25T13:24:55Z – 2026-10-25T13:28:53Z |

## Commands and results

| # | Environment / command | UTC | Observed | Original Gate 3 |
|---|---|---|---|---|
| 1 | Windows: `$env:PYTHONPATH="src;tests"; py -3 -B -m pytest tests -p no:cacheprovider -rfEs` | 13:24:55Z – 13:28:53Z | **368 passed, 27 skipped, 0 failed, 0 errors** | 368 passed, 27 skipped, 0 failed, 0 errors |
| 2 | WSL: `PYTHONPATH=src:tests python3 -B -m unittest tests.test_series tests.test_series_repetitions` | 13:24:55Z – 13:25:17Z | 61 tests, OK | 61 tests, OK |
| 3 | WSL: `PYTHONPATH=src:tests python3 -B -m unittest tests.test_series_repetitions.A_PilotReproduction -v` | 13:25:17Z – 13:25:25Z | 2 tests, OK (ran, not skipped) | 2 tests, OK |
| 4 | WSL, user `cclab`, in memory: `series.build_spec(SeriesConfig.from_json("/home/cclab/cclab-pilot/series.json"))` + `generate_schedule`, compared with the frozen `/home/cclab/cclab-pilot/series/pilot-v1/spec.json` and `schedule.json` | 13:25:26Z – 13:25:28Z | full spec and full schedule equal | — (added check) |

The 27 skips in command 1 are environment-only, identical to the original:

| Count | Tests | Reason |
|---|---|---|
| 15 | `test_evaluator_sandbox` | need Linux plus the pinned `cclab` sandbox runtime |
| 10 | `test_process_control` | need Linux `/proc` |
| 2 | `test_series_repetitions` pilot-reproduction tests | Windows cannot represent the P-TS-01 `node_modules/.bin` symlinks. These same two tests ran and passed in WSL (command 3) |

## Frozen pilot identities

| Identity | Frozen value (`PILOT_V1_CLOSEOUT.md` §2) | Re-check |
|---|---|---|
| `spec_hash` | `90628ef77d385c98ed5ee8ec1f7c6e9a709da91c6cb11c2cdff5ccb0736b4b81` | reproduced exactly |
| `schedule_hash` | `ebd175cddd622153138323d8116a06e001650f96960cf03bd16de1a5bd04bfe9` | reproduced exactly |

All six cells are reproduced exactly in position, task, configuration and repetition:

| Pos | `cell_id` | Cell | Re-check |
|---|---|---|---|
| 1 | `cell-fe764020303430fd` | P-TS-01 × C0 × 1 | reproduced |
| 2 | `cell-be645426fc613334` | P-PY-01 × C1 × 1 | reproduced |
| 3 | `cell-e5edb916959ba3d7` | P-TS-01 × C2 × 1 | reproduced |
| 4 | `cell-af7114946671407f` | P-PY-01 × C2 × 1 | reproduced |
| 5 | `cell-c2708598bbb89ec1` | P-TS-01 × C1 × 1 | reproduced |
| 6 | `cell-7bb8b30547dbb18c` | P-PY-01 × C0 × 1 | reproduced |

## FINAL 54-cell model-free dry schedule

**Original Gate 3 (2026-10-09).** A dry FINAL-namespace series ran in a temporary directory, with
six synthetic `F-G3-*` tasks and a throwaway seed. It confirmed:

- 54 cells in three contiguous blocks of 18;
- every (task, configuration, repetition) exactly once, with unique `cell_id`s;
- `freeze` / `plan` / `status` working through both the API and the CLI;
- 0 attempts, and `run-next` without `--execute` refused;
- an independent recomputation of the per-block derivation matched.

**No dry schedule hash was recorded then.** That run's seed and tasks were synthetic by design, so
there is no original dry-schedule identity to reconstruct, and none is claimed here.

**This re-check.** The same properties are re-proven by command 1, which passed in full. The
covering tests are in `tests/test_series_repetitions.py`:

- `test_54_cells_three_complete_blocks`
- `test_documented_per_block_derivation`
- `test_repetition_is_part_of_cell_identity`
- `test_same_spec_same_schedule`
- `test_two_independent_freezes_agree`
- `test_seed_controls_order_not_cell_set`
- `test_plan_resume_and_replacement_with_repetitions`
- `test_freeze_plan_status_model_free`

The real Study-01 seed was **not** used, and no Study-01 schedule was generated.

## Scope of this record

It covers:
- model calls: 0;
- harness, treatment and task-package bytes: unchanged;
- no series root, spec, schedule or attempt created.

The Study-01 schedule and `study_snapshot_hash` belong to Gate 6. The operator decisions are in
`docs/STUDY_01_GATE5_DECISIONS.md`.
