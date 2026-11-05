# Study-02 Final Report — CodeAgent ConfigLab

## 1. Executive summary

Study-02 tested whether an explicit, tested two-phase plan-then-approve workflow (C2) changes contract-compliant task completion relative to the same substantive repository instructions without that workflow (C1), on a new set of 12 distinct coding tasks across six repository families (a robustness/generalization replication of Study-01's RQ2, not a forced replication exercise). **The quality-degradation effect Study-01 found (C2 markedly worse) did not recur on this task set**: C1 resolved 12/24 (50.0%), C2 resolved 13/24 (54.17%), a negligible, opposite-sign difference driven by a single task. Both configurations achieved 100% functional (acceptance+regression) completion. **The explicit workflow's candidate-time cost did reproduce, consistently and more strongly than in Study-01.** A severe floor/ceiling structure between the two languages in this task set materially limits how much this design can say about a broader quality contrast — discussed in full below rather than smoothed over.

## 2. Research question

> Under an identical frozen repository `CLAUDE.md` for each task and fully candidate-visible task constraints, does the explicit two-phase plan-then-approve workflow (C2) change contract-compliant task completion relative to the same substantive `CLAUDE.md` without that workflow (C1) on a new set of 12 distinct coding tasks across six repository families?

C1 is not "no planning" — it still performs any planning the candidate chooses, unstructured. C2 measures the incremental, tested two-phase workflow specifically, not Claude Code's built-in Plan Mode.

## 3. Experimental design

12 distinct tasks (6 Python, across families `throttlekit`, `stocktrack`, `configmerge`; 6 TypeScript, across families `dedupe-cache`, `qs-normalize`, `mini-queue`) across 6 repository families (2 tasks per family) × 2 configurations (C1/C2) × 2 repetitions = 48 planned cells (24 C1, 24 C2). One cell (position 36, task `S2-TS-BUG-01`, configuration C2, repetition 2) had its original attempt externally interrupted by a Claude subscription usage-limit before any task work occurred in phase 2 — a `valid`, `not_countable:external_interruption` outcome under the frozen policy, not a task failure. A single operator-approved replacement was executed under identical frozen treatment and reached a valid, countable outcome. **The replacement does not create a 49th experimental cell** — the invalid original is preserved as provenance and excluded from all result tables; the study remains 48 planned cells.

## 4. Treatments

- **C1** — a frozen repository `CLAUDE.md` present in the working copy from the first moment of the run; no planning wrapper or approval message.
- **C2** — the same frozen `CLAUDE.md`, plus a scripted two-phase workflow: phase 1 runs the agent in a read-only envelope with a frozen planning-wrapper prompt (verified to make zero file changes); phase 2 resumes the *same* session with a frozen, fixed approval message and a write-capable envelope. Both phases share one 900-second wall-clock budget (phase-1 consumption reduces phase-2's remaining budget; phase-2 never receives a fresh 900 seconds).

All treatment content is frozen and hash-verified per attempt; no attempt in the dataset showed a treatment-provenance violation.

## 5. Outcome definitions

- **`resolved`** (primary, preregistered): `valid ∧ countable ∧ acceptance=pass ∧ regression=pass ∧ integrity=clean`.
- **`functional_pass`** (secondary, preregistered): `valid ∧ countable ∧ acceptance=pass ∧ regression=pass`, integrity reported separately rather than used as an exclusion criterion.
- **Timing**: C1 uses the single agent-process elapsed time; C2 uses phase-1 elapsed + phase-2 elapsed (the inter-phase gap, evaluator time, setup, and cleanup are excluded).
- Acceptance, regression, and integrity are also reported descriptively per observation. Task is the primary independent analysis unit (12 units); the 48 cells are not 48 independent samples.

## 6. Analysis method

All results are descriptive and paired/task-aware. **No significance test, p-value, confidence interval, or bootstrap was computed** — the frozen study protocol does not call for inferential testing on this design, and none is implied by these numbers. Matched pairs are keyed by `task_id × repetition` (24 pairs).

## 7. Primary result

| Config | Resolved | Total | Rate |
|---|---|---|---|
| C1 | 12 | 24 | 50.00% |
| C2 | 13 | 24 | 54.17% |

**Matched transitions (24 pairs)**

| C1 | C2 | Count |
|---|---|---|
| resolved | resolved | 12 |
| unresolved | resolved | 1 |
| resolved | unresolved | 0 |
| unresolved | unresolved | 11 |

Net matched success-rate difference: **+4.17 percentage points** (+1 cell). **The Study-01 C1-to-C2 reduction in the frozen composite `resolved` endpoint did not recur on this task set.** This is a non-replication finding — it is not evidence that the explicit workflow improves correctness, and the entire cell-level difference traces to a single task (§8).

## 8. Task-level result (primary analysis unit, 12 tasks)

1 of 12 tasks improved under C2 (`S2-PY-BUG-02`, 0/2 → 1/2), 11 tied, 0 worsened. Median task-level difference: 0; mean: +0.083 (out of 2). All 6 TypeScript tasks are tied at ceiling (2/2 both configurations); 5 of 6 Python tasks are tied at floor (0/2 both configurations). Full table: `docs/study02_data/task_results.csv`.

## 9. Paired task×repetition transitions

24 matched pairs: 12 both-resolved, 1 C2-only, 0 C1-only, 11 both-unresolved. Full table: `docs/study02_data/paired_transitions.csv`.

## 10. Secondary functional result

| Config | functional_pass |
|---|---|
| C1 | 24/24 |
| C2 | 24/24 |

**No C1/C2 difference was observed in acceptance/regression-defined functional completion.** The entire primary `resolved` difference is attributable exclusively to the integrity axis, not to acceptance or regression. `functional_pass` is a preregistered secondary endpoint, reported for transparency — it does not replace or override the primary `resolved` endpoint.

## 11. Integrity decomposition

| Config | Integrity clean | Integrity fail |
|---|---|---|
| C1 | 12/24 | 12/24 |
| C2 | 13/24 | 11/24 |

All 23 unresolved observations across both configurations were classified `protected_path_modified`; `out_of_tree_write_detected` was never observed. **Unlike Study-01 — where the relevant protected-path restriction was not disclosed to candidates — Study-02's protected-path criterion was prospectively candidate-visible and validated before execution.** These integrity failures therefore remain legitimate primary-endpoint failures under the frozen protocol, not a disclosure-gap artifact, and are not reclassified or discarded. Persisted change records show the candidate modified or created paths protected by the candidate-visible study contract (predominantly in-package source files, occasionally ad hoc test files under `scratch_tests/`); no intent or rule-violation motive is claimed. Full table: `docs/study02_data/integrity_failures.csv`.

## 12. Timing result

All 48 valid/countable selected observations are used (timing is not conditioned on `resolved`).

| Config | N | Median | Mean | Min | Max |
|---|---|---|---|---|---|
| C1 | 24 | 36.73s | 38.91s | 14.61s | 97.65s |
| C2 | 24 | 63.75s | 75.03s | 37.89s | 151.75s |

C2 was slower in **24/24** matched pairs and in **12/12** task-level medians. Median paired difference ≈ **+32.95s**; median paired ratio ≈ **1.996×**. The planning phase accounted for a median of **60.6%** of C2's total candidate time. **The explicit two-phase workflow produced a consistent candidate-time cost across both studies** (Study-01: 18/18 pairs, ≈1.53×; Study-02: 24/24 pairs, ≈2.0×) — a task-set-specific descriptive finding, not a claim of a universal 2× slowdown.

## 13. Exploratory language/repository-family structure (EXPLORATORY / DESIGN LIMITATION)

| Language | n | Resolved |
|---|---|---|
| typescript | 24 | 24 |
| python | 24 | 1 |

TypeScript observations resolved in 24/24 cases (both configurations) — a ceiling with no observable treatment contrast. Python observations resolved in 1/24 cases (both configurations combined) — near floor, driven almost entirely by the integrity criterion. **Resolution outcomes were highly concentrated by language/repository-family structure, creating a strong floor/ceiling limitation for interpreting broad treatment effects.** Language and repository family are structurally confounded in this design (each language's three families are disjoint from the other language's); this pattern is reported as an observed structural limitation, not attributed causally to programming language, and does not invalidate the frozen primary result in §7. Full table: `docs/study02_data/exploratory_strata.csv`.

## 14. Study-01 comparison (descriptive only — never pooled)

| | Study-01 | Study-02 |
|---|---|---|
| Primary C1 | 16/18 (88.9%) | 12/24 (50.0%) |
| Primary C2 | 12/18 (66.7%) | 13/24 (54.17%) |
| C2−C1 | −4 cells / −22.2pp | +1 cell / +4.17pp |
| Functional pass C1/C2 | 17/18 (post-hoc) / 16/18 (post-hoc) | 24/24 (preregistered) / 24/24 (preregistered) |
| Timing: pairs C2-slower | 18/18 | 24/24 |
| Timing: median ratio | ≈1.527× | ≈1.996× |

No denominators are pooled and no combined effect is computed. Study-01's functional-pass breakdown was a **post-hoc** sensitivity analysis; Study-02's was a **prospectively preregistered** secondary endpoint — the two are not methodologically identical. A shared integrity category label (`protected_path_modified`) across the two studies does not imply a replicated mechanism: Study-01's relevant restriction was not candidate-visible, while Study-02's was.

## 15. Interpretation

- **Primary endpoint**: **non-replication** — the Study-01 quality-degradation effect did not recur here.
- **Timing**: **directional robustness support** — the candidate-time cost reproduced, and more strongly.
- **Overall**: mixed, endpoint-dependent evidence. A robust, reproducible time cost sits alongside a non-reproduced quality effect, further complicated by the language/family floor-ceiling structure (§13) that limits this design's power to detect a true quality contrast in half of this task set.

## 16. Limitations

- Only 12 distinct task units (not 48 independent samples); 2 tasks per repository family, receiving byte-identical treatment.
- Only Python and TypeScript represented, with a severe floor/ceiling structure between them (§13) that is fully confounded with repository family.
- Synthetic mini-repositories, not real-world codebases.
- Single model alias (`claude-sonnet-5`), single effort level (`high`), single contemporaneous execution period; no claim of backend identity with Study-01 merely from the shared model-alias string.
- Two repetitions per task×configuration characterize within-task variability, not an added independent sample.
- Integrity failures dominate the composite `resolved` endpoint entirely (acceptance/regression are at ceiling in both configurations).
- No inferential statistical claims are made anywhere in this report.
- Study-02 tests the specific, tested, explicit two-phase workflow (C2) as implemented here — not "planning in general," and not Claude Code's built-in Plan Mode.

## 17. Study-03 decision

**No Study-03 intervention is indicated by this evidence alone.** The preregistered standard for an intervention study is a pattern that is simultaneously reproducible, treatment-associated, actionable, and non-artifactual. Here: the originally-hypothesized quality-degradation tradeoff did not reproduce; functional degradation was absent; the timing cost reproduced strongly but is not currently paired with a reproduced quality cost; and the integrity pattern, while present as a rate, is overwhelmingly associated with language/repository-family structure rather than the C1/C2 contrast — artifactual with respect to the treatment. A future robustness study would benefit from rebalancing the task set against the floor/ceiling structure identified here before attempting another primary-endpoint comparison.

## Public data tables

The following CSVs under `docs/study02_data/` back the figures in this report:

- [config_summary.csv](../study02_data/config_summary.csv) — per-configuration resolved/functional-pass/acceptance/regression/integrity counts underlying §7, §10, §11.
- [task_results.csv](../study02_data/task_results.csv) — per-task resolved-of-2 counts and configuration contrasts underlying §8.
- [paired_transitions.csv](../study02_data/paired_transitions.csv) — matched task×repetition success pairs underlying §9.
- [paired_timing.csv](../study02_data/paired_timing.csv) — matched task×repetition timing pairs underlying §12.
- [task_timing.csv](../study02_data/task_timing.csv) — per-task median timing and configuration contrasts underlying §12.
- [integrity_failures.csv](../study02_data/integrity_failures.csv) — the 23 integrity-fail observations with descriptive affected-path detail underlying §11.
- [exploratory_strata.csv](../study02_data/exploratory_strata.csv) — language/task-type/repository-family descriptive rollups underlying §13.

Public tables omit internal attempt-ID columns; `position`/`task_id`/`configuration`/`repetition` remain as the public key, sufficient to verify every figure above against the hashes in §18.

## 18. Reproducibility / provenance

- Frozen repository HEAD at publication: `7ffed8d5ccd663578e543a606bded083b4d701b1`.
- Frozen Study-02 snapshot hash: `3d7f238963577fb3f99ea675e6e70c2a0611ac29d5c7d36af4a9deface5a0a37`.
- Selected-observations hash: `aa1488c8956706dab8305a56d13e4fa7c7b4187e14d23cc714cc3511bdba4887`.
- Attempt-lineage hash: `f2ab467111f1ccd473381541b2158aae967309546f05c31d6cdb0634d9ae3a17`.
- Machine-readable result lock: `docs/STUDY_02_RESULTS.json`.
- Protocol: `studies/study02/STUDY_02_PROTOCOL.md`.
- All headline figures in this report were independently re-derived from the frozen selected-observation dataset across multiple structurally distinct aggregation passes before publication, with exact agreement.
