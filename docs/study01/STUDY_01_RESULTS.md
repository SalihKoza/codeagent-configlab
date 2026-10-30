# Study-01 Final Report — CodeAgent ConfigLab

## 1. Executive summary

Study-01 tested whether two increasingly elaborate forms of agent scaffolding — a repository `CLAUDE.md` (C1), and that same `CLAUDE.md` plus an explicit two-phase plan-then-approve workflow (C2) — changed task outcomes or execution time relative to a plain baseline (C0), on six fixed coding tasks run three times each. Under the frozen, pre-registered composite `resolved` outcome: adding `CLAUDE.md` alone (C1 vs. C0) produced no net change in matched task success and increased run time in most matched observations. Adding the explicit planning workflow on top of `CLAUDE.md` (C2 vs. C1) reduced matched task success and increased run time in every matched observation.

A post-hoc verification pass (§8a) found that a meaningful share of that second result traces to one component of the composite outcome — an integrity (protected-path) criterion that was consistently enforced but not disclosed to the candidate — rather than to acceptance/regression (functional) failure. The frozen result is retained unchanged; a separately labeled, descriptive sensitivity table is included to make this transparent. See §15 for the full six-task scope caveat.

## 2. Research questions

- **RQ1** (primary): C1 vs. C0 — effect of the frozen repository `CLAUDE.md` relative to baseline.
- **RQ2** (primary): C2 vs. C1 — incremental effect of the explicit two-phase planning workflow, holding `CLAUDE.md` constant.
- **Secondary** (descriptive only, not a third RQ): C2 vs. C0, the combined-treatment contrast.

## 3. Experimental design

6 tasks × 3 configurations (C0/C1/C2) × 3 repetitions = 54 planned cells, executed by a dedicated harness (`codeagent_configlab`) that spawns a real, separate Claude Code CLI process per cell inside a disposable sandbox. Repetitions characterize within-task run-to-run variability (model execution is not seedable); they are not additional independent task samples. One cell (Cell 1) suffered an infrastructure-level authentication failure on its first attempt and was re-run once under an identical, operator-approved replacement policy (see §5) — the study remains 54 planned cells, not 55.

## 4. Treatments

- **C0** — no benchmark-specific `CLAUDE.md`, planning wrapper, or approval message.
- **C1** — a frozen, generic repository `CLAUDE.md` (conventions-only) present in the working copy; no planning wrapper or approval message.
- **C2** — the same frozen `CLAUDE.md`, plus a scripted two-phase workflow: phase 1 runs the agent in a read-only envelope with a frozen planning-wrapper prompt (verified to make zero file changes); phase 2 resumes the *same* session with a frozen, fixed continuation message ("Your plan is approved. Proceed with the implementation now...") and a write-capable envelope. Both phases share one 900-second wall-clock budget.

All treatment content is frozen and hash-verified per attempt; no attempt in the dataset showed a treatment-provenance violation. **C2 refers specifically to the two-phase workflow tested here, not to "explicit planning" in general; C1's absence of this workflow does not imply C0 performs no internal reasoning of its own.**

## 5. Dataset and replacement handling

55 total attempts were persisted: 54 original (one per planned cell) + exactly 1 replacement. The replacement applies only to Cell 1 (task `F-PY-BUG-01`, configuration C2, repetition 1), whose original attempt failed with an infrastructure authentication error (HTTP 401) before any task work occurred — a harness/infrastructure failure, not a task outcome. Per the pre-approved replacement policy (max one replacement per cell, requiring operator approval), a single replacement attempt was executed under identical frozen treatment and reached a valid, countable outcome. **The replacement does not create a 55th experimental cell** — the invalid original is preserved as provenance and excluded from all efficacy/timing results.

## 6. Outcome definitions

- **`resolved`** (primary binary outcome, pre-existing definition, not redefined here): `valid ∧ acceptance=pass ∧ regression=pass ∧ integrity=clean`. This composite remains the frozen primary outcome throughout this report.
- **Timing**: C0/C1 use the single agent-process elapsed time; C2 uses phase-1 elapsed + phase-2 elapsed (the gap between phases is excluded, and the evaluator's own wall-clock duration is never used as a performance metric).
- Refactor tasks additionally expose a **structural** check, reported as its own column, never folded into `resolved`.
- Changed-file count and added/deleted line counts are reported only as descriptive change-footprint metrics, never as quality signals.

## 7. Analysis method

All results are descriptive and paired/task-aware. **No significance test, p-value, confidence interval, or bootstrap was computed** — the frozen study protocol explicitly rules out inferential testing on this design. Matched pairs are keyed by `task_id × repetition` (18 pairs per contrast). Every result is reported task-by-task before any aggregate figure.

> **The benchmark contains 54 cell observations but only six distinct task units. Three repetitions per task/configuration characterize within-task run variability; they do not create 18 independent task samples per configuration.**

## 8. RQ1 — C1 vs. C0 (frozen primary result)

**Marginal success**

| Config | Resolved | Total | Rate |
|---|---|---|---|
| C0 | 16 | 18 | 88.9% |
| C1 | 16 | 18 | 88.9% |

**Matched transitions (18 pairs)**

| C0 | C1 | Count |
|---|---|---|
| resolved | resolved | 15 |
| unresolved | resolved | 1 |
| resolved | unresolved | 1 |
| unresolved | unresolved | 1 |

Net matched success-rate difference: **0.0 percentage points**. 1 task-level improvement, 1 task-level decline, 4 tasks tied (median and mean task-level difference = 0). Agent time increased under C1 in 16 of 18 matched pairs and in all six task-level median timings (median paired diff ≈+10.4s, median ratio ≈1.33×).

**Interpretation (within this benchmark only):** adding the frozen repository `CLAUDE.md` produced no net change in matched task success — the one task that improved was offset by one that declined — while consistently increasing run time.

## 9. RQ2 — C2 vs. C1 (frozen primary result)

**Marginal success**

| Config | Resolved | Total | Rate |
|---|---|---|---|
| C1 | 16 | 18 | 88.9% |
| C2 | 12 | 18 | 66.7% |

**Matched transitions (18 pairs)**

| C1 | C2 | Count |
|---|---|---|
| resolved | resolved | 11 |
| unresolved | resolved | 1 |
| resolved | unresolved | 5 |
| unresolved | unresolved | 1 |

Net matched success-rate difference: **−22.2 percentage points**. 0 task-level improvements, 3 task-level declines, 3 tasks tied (median task-level difference −0.5, mean ≈−0.667). Agent time increased under C2 in **all 18 of 18** matched pairs and in all six task-level median timings (median paired diff ≈+35.5s, median ratio ≈1.53×).

**Interpretation (within this benchmark only):** adding the explicit two-phase planning workflow, on top of the identical `CLAUDE.md` treatment, coincided with lower matched success and uniformly higher run time in this task set, under the frozen composite outcome. **A verified post-hoc review (§8a below) found that most of this success-rate gap is attributable to one component of that composite outcome rather than to functional (acceptance/regression) failure — read §8a before drawing conclusions from the −22.2 pp figure alone.**

## 8a. Post-hoc contract-visible functional sensitivity (descriptive supplement — not preregistered, does not replace §9)

This section was **not** part of the preregistered Study-01 analysis. It is included because an exploratory post-hoc review of the unresolved observations found that the frozen `resolved` criterion's integrity component was enforced consistently but was not disclosed to the candidate in any task-visible document (see §12). It is a transparency supplement only and does not change, replace, or supersede the frozen RQ1/RQ2 results in §8–§9.

Five selected observations (all 5 of Study-01's integrity failures) passed acceptance and passed regression but failed the integrity axis (`protected_path_modified`): C0: 0, C1: 1, C2: 4. In every one of the 5, the mutation was the agent adding new test coverage to a file the harness treats as protected for that task — never deleting, weakening, or disabling an existing test. The protected-path restriction was verified not to appear in any of the three affected tasks' public statements, and the closest related guidance (`CLAUDE.md`, C1/C2 only — "do not weaken, skip or delete existing tests to make them pass") addresses a different action than the one observed. The evaluator was confirmed to apply the identical rule and routine across C0/C1/C2 with no configuration-specific logic — this is a disclosure gap, not an evaluator defect or an inconsistently-applied rule.

| Configuration | Functional pass | Functional fail | Integrity clean | Integrity nonclean | Frozen resolved |
|---|---:|---:|---:|---:|---:|
| C0 | 16/18 | 2/18 | 18/18 | 0/18 | 16/18 |
| C1 | 17/18 | 1/18 | 17/18 | 1/18 | 16/18 |
| C2 | 16/18 | 2/18 | 14/18 | 4/18 | 12/18 |

*Functional pass = valid ∧ acceptance=pass ∧ regression=pass, with integrity reported separately rather than used as an exclusion criterion. This is a descriptive view only, not an alternative primary outcome.*

| Contrast | Functional-pass difference | Frozen `resolved` difference |
|---|---|---|
| C1 − C0 | +1 cell | 0 cells (0.0 pp) |
| C2 − C1 | **−1 cell** | **−4 cells (−22.2 pp)** |
| C2 − C0 | 0 cells | −4 cells (−22.2 pp) |

**Three of the four cells accounting for the frozen C2−C1 resolved gap are attributable to the undisclosed protected-path criterion rather than acceptance/regression failure.** Separately, RQ1's frozen 0.0 pp result partly reflects an offsetting pattern: C1 had one more functional-pass cell than C0, but also one more integrity-nonclean cell, netting to zero. Full detail: `docs/study01_data/integrity_sensitivity.csv`.

**This does not mean "planning reduced coding correctness by 22.2 percentage points," that "planning made Claude Code much worse," that "C2 generated lower-quality code," or that "CLAUDE.md had no benefit."** The frozen composite result (§9) stands as computed; this section exists so a reader can see how much of its magnitude traces to a criterion the candidate could not have known about, separately from functional task completion.

## 10. Secondary C2 vs. C0 (descriptive combined-treatment contrast)

Not a third research question. C0 88.9% → C2 66.7% (−22.2 pp); 0 task-level improvements, 3 declines, 3 tied; agent time higher under C2 in 17 of 18 matched pairs and in all six task-level medians. This pattern tracks RQ2 rather than RQ1, since RQ1 alone showed ~no effect — the combined decline from baseline is attributable mainly to the C2-specific increment (see §8a for how much of that increment is integrity-driven).

## 11. Timing results

All figures use **all 54 countable observations** (not resolved-only), per the frozen timing definition (§6):

| Config | N | Median | Mean | Min | Max |
|---|---|---|---|---|---|
| C0 | 18 | 34.5s | 47.5s | 12.4s | 140.8s |
| C1 | 18 | 46.8s | 55.6s | 12.7s | 153.2s |
| C2 | 18 | 76.7s | 89.6s | 25.0s | 216.2s |

Paired median differences: C1−C0 ≈ +10.4s (median ratio ≈1.33×); C2−C1 ≈ +35.5s (median ratio ≈1.53×); C2−C0 ≈ +36.0s (median ratio ≈2.02×). A resolved-only timing table was also computed and is directionally consistent, but is explicitly treated as supplementary (conditioning on outcome), never primary.

## 12. Failure-axis analysis

10 of 54 selected observations are unresolved — exactly two axes account for all 10, never combined:

- **5 integrity failures** (`protected_path_modified`): 4 under C2, 1 under C1, 0 under C0. See §8a for the verified disclosure-gap finding and sensitivity table.
- **5 acceptance (behavioral) failures**: all 5 belong to the single task `F-TS-REF-01`.

Regression failed in 0 of 54 observations; there were no evaluator-infrastructure errors in the selected dataset.

| Config | Integrity non-clean | Acceptance failures |
|---|---|---|
| C0 | 0 | 2 |
| C1 | 1 | 1 |
| C2 | 4 | 2 |

### Post-hoc exploratory note on the acceptance failures

*(Post-hoc exploratory analysis — not preregistered, included for context only.)* All five acceptance failures were independently traced to one shared implementation pattern: the candidate built the task's operation registry as a plain JavaScript object instead of a `Map`, which is vulnerable to prototype-chain lookups (`toString`, `__proto__`, and similar names resolve to an inherited member instead of triggering the required error). The public task statement explicitly required immunity to this exact hazard and named two of the triggering values directly. The four comparison attempts that passed used a `Map` and were unaffected. The task's structural check passed in all 9 `F-TS-REF-01` cells regardless of outcome because it is a purely static analysis of code shape and does not execute the code, so it cannot detect this class of runtime defect. Failures and passes occurred across all three configurations (C0, C1, and C2 each had both an outcome of each kind across repetitions), tracking the per-attempt implementation choice rather than configuration — this finding should **not** be read as evidence that TypeScript refactors are generally harder, that refactors are generally unreliable, that any one configuration caused the issue, or as proof of model randomness; it is a single-task observation from six repeated attempts.

## 13. Refactor-task observations

Both refactor tasks keep acceptance, structural, regression, and integrity as independent axes:

- `F-PY-REF-01`: 9 of 9 cells resolved across all configurations/repetitions.
- `F-TS-REF-01`: 5 of 9 cells unresolved; structural checks pass in all 9 cells and regression/integrity are clean in all 9 — every failure is isolated to the acceptance (behavioral) axis (see §12 for the shared root cause). Repetition 1 resolves under every configuration (C0/C1/C2); repetitions 2–3 fail across all three configurations roughly evenly.

## 14. Task-level heterogeneity

| Task | C0 | C1 | C2 | C1−C0 | C2−C1 | C2−C0 |
|---|---|---|---|---|---|---|
| F-PY-BUG-01 | 3/3 | 3/3 | 3/3 | 0 | 0 | 0 |
| F-PY-FEAT-01 | 3/3 | 2/3 | 2/3 | −1 | 0 | −1 |
| F-PY-REF-01 | 3/3 | 3/3 | 3/3 | 0 | 0 | 0 |
| F-TS-BUG-01 | 3/3 | 3/3 | 2/3 | 0 | −1 | −1 |
| F-TS-FEAT-01 | 3/3 | 3/3 | 1/3 | 0 | −2 | −2 |
| F-TS-REF-01 | 1/3 | 2/3 | 1/3 | +1 | −1 | 0 |

Half the tasks show no change across all three configurations under the frozen outcome. Each language × task-type combination has exactly one task in this design, so this is a six-task descriptive pattern, not a basis for a language- or task-type-general claim.

## 15. Limitations

- Only **six task units**; three repetitions per task/configuration characterize within-task run variability, not 18 independent samples.
- Synthetic benchmark tasks, one per language × task-type cell — no claim that Python/TypeScript or bug/feature/refactor tasks are differentially affected in general.
- Single frozen model (`claude-sonnet-5`), single harness/version, single environment — results do not generalize beyond this exact configuration.
- No significance testing, confidence interval, or bootstrap was performed or is implied anywhere in this report; the frozen protocol explicitly rules this out for a six-task design.
- Findings do not generalize to real-world repositories, to coding agents in general, or to planning/CLAUDE.md as techniques in general. C2 refers specifically to the two-phase workflow tested here, not to "explicit planning" generically; C1's design does not imply C0 performs no internal planning of its own.
- No causal claim is made from C2's integrity concentration alone (§8a) — the sensitivity table is descriptive.
- **The frozen Study-01 integrity criterion included a protected-path restriction that was not disclosed to candidates.** This affected five observations and materially influenced the composite `resolved` contrast for RQ2. The frozen result is retained for protocol integrity (§9) and supplemented with the separately labeled functional sensitivity analysis in §8a. Future studies can test whether disclosing this restriction prospectively changes the pattern.

## 16. Conclusions

Within this controlled, six-task benchmark, under the frozen composite outcome: adding a repository `CLAUDE.md` (RQ1) changed neither net task success nor the balance of task-level outcomes, while modestly increasing run time. Adding an explicit two-phase planning workflow on top of that same `CLAUDE.md` (RQ2) coincided with lower matched task success and uniformly higher run time. A verified post-hoc review found that most of that success-rate gap traces to an integrity criterion that was consistently enforced but not disclosed to the candidate, rather than to functional (acceptance/regression) failure — functional-pass rates were far closer across configurations (C0 16/18, C1 17/18, C2 16/18) than the frozen composite numbers alone suggest. **Study-01's broader lesson is that coding-agent configurations should be evaluated across multiple outcome dimensions (functional correctness, integrity/scope adherence, execution time) rather than reduced to one aggregate success number** — more scaffolding did not automatically improve the frozen composite outcome and carried a measurable execution-time cost, but the apparent C2 deficit was strongly shaped by a criterion visibility gap rather than functional failure alone. These are descriptive findings about this exact benchmark and do not establish that more agent scaffolding, or explicit planning generally, is harmful.

## Public data tables

The following CSVs under `docs/study01_data/` back the figures in this report, one row-level table per axis of analysis:

- [cells.csv](../study01_data/cells.csv) — all 54 analyzed cells, one row each, with every outcome axis, timing, and provenance field.
- [paired_success.csv](../study01_data/paired_success.csv) — matched task×repetition success pairs underlying the RQ1/RQ2/secondary contrasts.
- [paired_timing.csv](../study01_data/paired_timing.csv) — matched task×repetition timing pairs underlying the RQ1/RQ2/secondary timing contrasts.
- [task_success.csv](../study01_data/task_success.csv) — per-task resolved-of-3 counts and configuration contrasts.
- [task_timing.csv](../study01_data/task_timing.csv) — per-task median timing and configuration contrasts.
- [unresolved_observations.csv](../study01_data/unresolved_observations.csv) — the 10 unresolved cells with their failing axis and reason.
- [integrity_sensitivity.csv](../study01_data/integrity_sensitivity.csv) — the post-hoc functional-vs-integrity breakdown underlying §8a.

## 17. Reproducibility/provenance

- Frozen repository HEAD: `03eb4b4b986dcc68cd923cd71b427b0e6d240869`.
- Frozen Study-01 snapshot hash: `3ad54204775e12f55e14c149b2e9bc6e8e9d6194529e47e97f5fc2ae44f32d01`.
- Public reproducibility data: `docs/study01_data/` (aggregate tables; see that directory's contents for the per-table list).
- Machine-readable result lock: `docs/STUDY_01_RESULTS.json`.
- Protocol: `docs/STUDY_01_PROTOCOL.md`.
- All headline figures in this report, including the §8a sensitivity table, were independently re-derived and verified directly against the canonical attempt-level artifacts before publication.
