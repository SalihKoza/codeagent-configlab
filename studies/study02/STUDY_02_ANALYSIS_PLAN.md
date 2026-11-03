# Study-02 Analysis Plan (FROZEN, Gate 7I)

## 1. Outcome table

| Outcome | Status | Definition |
|---|---|---|
| **`resolved`** (primary) | Preregistered | `valid ∧ acceptance=pass ∧ regression=pass ∧ integrity=clean`, scored only on countable observations |
| **`functional_pass`** (secondary) | Preregistered | `valid ∧ acceptance=pass ∧ regression=pass`, integrity reported separately |
| Acceptance | Preregistered secondary | `acceptance ∈ {pass, fail, error, not_run}`, reported descriptively per observation |
| Regression | Preregistered secondary | `regression ∈ {pass, fail, error, not_run}`, reported descriptively per observation |
| Integrity | Preregistered secondary | `integrity ∈ {clean, protected_path_modified, out_of_tree_write_detected}` per observation |
| Total candidate time | Preregistered secondary | C1: single `elapsed_seconds`; C2: phase-1 + phase-2 summed |
| C2 phase-1 (planning) candidate time | Preregistered secondary | — |
| C2 phase-2 (implementation) candidate time | Preregistered secondary | — |
| Task-level resolved count out of 2 | Preregistered secondary | — |
| Paired task×repetition transitions | Preregistered secondary | 24 pairs |
| Language / task-type / repository-family patterns | Exploratory only | Descriptive; not a basis for a confirmatory claim |
| Repetition variability | Exploratory only | Descriptive |
| Resolved-only timing (if later reported) | Exploratory only | Descriptive |

**Excluded** (preregistered, not a post-hoc decision):
- Token/API-cost metrics — no pre-existing reliable measurement path that doesn't alter the study.
- Weighted/composite score (equivalently, "weighted quality score") — no score beyond the Boolean
  `resolved` primary endpoint and the `functional_pass` secondary endpoint.
- Generic quality proxies (line count, cyclomatic complexity, etc.) — gameable, weakly related to
  the stated goal.

## 2. Validity / eligibility / outcome-success separation

- **Run validity**: answers "was the attempt executed as specified."
- **Analysis eligibility**: answers "does this attempt count as the planned observation for its
  cell," derived automatically from run validity + agent outcome, never set independently.
- **Task success (`resolved`/`functional_pass`)**: computed only on countable observations.

These three questions are never merged. A non-countable attempt is never converted into a task
failure — it is reported as `no_valid_attempt` for that cell if no countable attempt exists, and
stays in the planned-cell denominator (48), never imputed or silently dropped. The denominator is
never silently narrowed from 24 planned cells per configuration (or 48 overall) to only the
countable observations — any gap is itself reported, not hidden.

## 3. Primary unit

`task` (12 units). Repetition (2 per task per configuration) characterizes within-task execution
variability, not additional independent samples.

## 4. Status

**FROZEN** at Gate 7I.
