# CodeAgent ConfigLab — Pilot Task Standard

Status: **draft for the pilot series `pilot-v1`, 2026-09-27.** Documentation only; no task package
exists yet. This standard defines what counts as a valid **pilot** task package. It is written so
that it can later serve as the basis for the six final tasks, but **nothing here becomes a final
decision automatically**: the final task standard is frozen separately (protocol §9, §12).

Terminology follows `docs/EXPERIMENT_PROTOCOL_V0.md` (MUST / SHOULD / OPEN). Every rule below is
tagged:

| Tag | Meaning |
|---|---|
| **[FROZEN]** | Already fixed by the protocol (F-number or § given). Restated here only as a pointer. |
| **[PILOT]** | Proposed for `pilot-v1`. Binding for the pilot series once `PILOT_PLAN.md` is frozen; **not** a final default. |
| **[OPEN-FINAL]** | Deliberately left open until the final freeze. |

Related documents: `docs/PILOT_PLAN.md` (how the pilot is executed), `docs/RUN_MANIFEST_V0.md`
and `schemas/run-manifest.schema.json` / `schemas/run-result.schema.json` (records),
`docs/HARNESS_READINESS_SPIKE.md` (harness topology).

---

## 1. Scope

- Applies to pilot tasks, IDs `P-…` [FROZEN §9, F16]. Pilot tasks are excluded from all final
  results and are never promoted into the final set (§12 of this document).
- A task package is **authored and validated without any model call**. The task validity gate
  (§11) runs only the evaluator on author-provided code states.
- A package that has not passed the validity gate MUST NOT be used in any agent run.

## 2. Package components

A task package is conceptually split into nine parts. The physical layout is decided when the first
package is implemented; it MUST follow the harness topology in
`docs/HARNESS_READINESS_SPIKE.md` ("Harness implication (topology)"): everything except the
per-run working copy lives under the harness root, which is `denyRead` in every agent sandbox
[FROZEN F9, A1].

| # | Component | Agent-visible? | Where it reaches the agent |
|---|---|---|---|
| 1 | Pristine fixture (repository at task start, incl. public tests, README) | **yes** (as a fresh copy) | per-run working copy |
| 2 | Public task statement | **yes** | stdin (C2: inside the fixed planning wrapper) |
| 3 | Treatment material (C1/C2 `CLAUDE.md`; C2 wrapper + approval message) | yes, **only in its own configuration** | WC root / stdin |
| 4 | Hidden acceptance tests (and structural checks, §10) | **no** | evaluator only |
| 5 | Hidden regression tests | **no** | evaluator only |
| 6 | Reference solution (+ alternative valid solutions, §8) | **no** | validity gate only |
| 7 | Evaluator configuration (test commands, protected paths, ignore list, evaluator timeout) | **no** | evaluator only |
| 8 | Validity evidence (§11) | **no** | results store |
| 9 | Metadata / version identity (§13) | **no** (hashes appear in manifests, which are outside the sandbox) | manifest |

Component 3 is treatment, not task: it is authored once per series, not per task
(`PILOT_PLAN.md` §8), and MUST NOT be stored inside a task package.

## 3. Public task statement

The statement is what a competent engineer would receive as an issue or feature request.

It MUST:

1. describe the required **observable behavior** (inputs → outputs, errors, or the structural
   outcome of a refactor);
2. give C0 **everything needed to attempt the task** — including any contract detail the hidden
   tests rely on (§6) and how to run the public tests if that is not obvious from the fixture;
3. state constraints a competent engineer legitimately needs (e.g. "public API signatures must not
   change", "no new runtime dependencies");
4. be **byte-identical** for C0, C1 and C2 of the same task [FROZEN F6, §3.3]; its SHA-256 is the
   manifest's `task_statement_hash`;
5. be written without reference to any treatment (no "as described in CLAUDE.md", no "after
   planning").

It MAY contain: a minimal reproduction, one or two examples, the names of the public functions /
modules concerned, the structural target of a refactor (§10), and explicit forbidden shortcuts
(§9).

It MUST NOT contain:

- implementation steps copied from, or specific to, the reference solution ("change line 12 to
  `<=`", "use a dict comprehension") when implementation freedom is intended;
- expectations that only the hidden tests know (§6);
- wording that assumes treatment material (C1/C2) or advantages a planning phase;
- hints to the evaluator's mechanics beyond what a normal issue states [FROZEN §5 last paragraph].

**Bad-pattern checklist** (author reviews the statement against each; any "yes" → rewrite):

| Pattern | Why invalid |
|---|---|
| A required edge case appears only in hidden tests and cannot be inferred from the statement + repository contract | secret requirement; measures luck, not engineering |
| "Modify function X exactly this way" where several correct fixes exist | tests compliance with the reference, not problem solving |
| Refers to a convention defined only in `CLAUDE.md` | C0 information disadvantage |
| Contains an identifier, comment or phrase copied from the reference diff that is not needed to state the problem | accidental solution leak |
| Asks for "clean" / "better" code without an objective criterion | not checkable (§10) |

## 4. Pristine fixture

The fixture MUST:

- be **small and synthetic** (pilot guidance: a handful of source files, a few hundred lines at
  most) with no irrelevant complexity;
- pin all dependencies (lockfile / exact versions); nothing is downloaded during a run (agent has
  no network [FROZEN §3.1]); dependency preparation follows O9 [OPEN-FINAL; pilot mechanism in
  `PILOT_PLAN.md` §15];
- run its public tests **deterministically and offline** (no wall-clock, randomness without a fixed
  seed, network, locale or filesystem-order dependence);
- have **one neutral baseline history**: a single commit with fixed author, date and message
  [FROZEN §4] — no reference solution, branches, tags, stashes or notes in `.git`;
- contain no hidden tests, reference material, evaluator files, outputs of previous runs, or
  names that hint at the experiment (task ID, configuration, "pilot", "hidden", "reference")
  [FROZEN §4, §5]; the harness additionally refuses a few obvious names
  (`workspace.FORBIDDEN_WC_NAMES`), which is a backstop, not a substitute;
- contain a short `README` stating how to run the public tests, identical in style across tasks of
  the same language. Repository facts that every configuration needs belong here, **not** in
  `CLAUDE.md` (see `PILOT_PLAN.md` §8);
- be identical for C0, C1 and C2 except for the intentional treatment file [FROZEN §4].

Identity: the fixture's content hash (`hashing.tree_hash`, which ignores `__pycache__`,
`.pytest_cache`, `node_modules`, `.git`) and the dependency lockfile hash are part of the task
version (§13). Because `tree_hash` ignores `.git` and `node_modules`, the baseline commit and the
installed dependency tree need their own recorded identity (§13).

## 5. Acceptance tests

Acceptance tests check the **requested new or fixed behavior**. They MUST:

- map one-to-one (or many-to-one) onto requirements stated in the public statement; each test
  carries a comment naming the statement sentence it checks;
- be deterministic and offline;
- check behavior through the public interface, not implementation style (no asserting on private
  helper names, line counts or formatting unless the statement requires it);
- never depend on the agent's self-report or on files the agent could have edited (§7).

For **bug fix / feature** tasks the pristine fixture MUST fail at least one acceptance test **for
the intended reason** — the assertion about the requested behavior fails. A failure caused by an
import error, missing fixture file, crashed runner or timeout is a **broken test**, not an unsolved
task, and blocks the gate. The validity evidence records the failing test IDs and the failure
message (§11).

For **refactor** tasks see §10.

## 6. Hidden tests

Hidden tests are the evaluator's acceptance and regression suites (plus refactor structural
checks). They MAY probe cases the public tests do not show; they MUST NOT create requirements.

**Author review question** — asked for every hidden test, answer recorded in the validity
evidence:

> *Could a competent engineer reasonably infer this expected behavior from the public task
> statement and the repository's existing contract (docstrings, types, README, public tests)?*

If the answer is **no**, the test is invalid: either the statement is extended (same text for all
configurations) or the test is removed.

Hidden tests are unreadable by the agent through every tool surface [FROZEN F9] and participate only
in the post-agent evaluator phase [FROZEN F10]. Their storage location is not fixed by this
standard beyond "under the harness root, outside the working copy" (topology above); the concrete
path is fixed when the evaluator is implemented (`PILOT_PLAN.md` §15, gap G5).

## 7. Regression tests and evaluator independence

Regression tests check behavior that must **remain** valid.

- The regression suite MUST pass on the pristine fixture (unless the statement explicitly changes
  that behavior — then those tests belong to acceptance) and on the reference solution.
- Regression results are recorded on their own axis. `acceptance` and `regression` are never
  merged into one score [FROZEN F11]; `resolved` is the derived boolean of protocol §6.

Evaluator independence (all [FROZEN §6, F10, F13] unless tagged):

- Evaluation runs only after the agent has ended, on a copy of the final working copy.
- **Protected paths** (public test files, test configuration, `conftest.py`, `package.json`
  `scripts`/`test` entry, runner config such as `pytest.ini`/`tsconfig` if used by tests) are
  restored to their pristine versions before hidden tests are added. The list is per task and
  frozen with it.
- A change to a protected path is recorded as `integrity=protected_path_modified` — a valid,
  unresolved **outcome**, not an invalid run.
- [PILOT] Dependencies used by the evaluator (Python environment, `node_modules`) come from the
  pristine, out-of-sandbox copy, not from the agent's working copy: `node_modules` is excluded from
  the tree hash and diff, so agent edits there would otherwise be invisible and could influence the
  verdict.
- Agent-modified public tests never decide success: the evaluator runs its own copies.

## 8. Reference solution

Every task MUST have a reference solution before it is accepted. It:

- demonstrates solvability and validates the acceptance and regression suites;
- is never agent-visible and never enters the fixture's git history;
- is **not a uniqueness requirement**: the evaluator MUST NOT require its exact structure unless
  the statement explicitly requires that structure.

[PILOT] Where more than one natural solution exists, the author SHOULD also write one short
**alternative valid solution** and show that it passes. This is required for refactor tasks (§10)
and recommended for others; it is the cheapest evidence that the evaluator is not over-fitted to
the reference.

## 9. Known-wrong solutions and forbidden shortcuts

**Known-wrong solutions.** A reference solution passing proves only that one valid solution passes;
it does not prove that the evaluator rejects bad ones. Each task therefore has **at least one**
small, plausible but inadequate solution that the evaluator MUST reject. Task-specific hand-written
cases are sufficient; no mutation-testing framework is required. Typical shapes:

- a bug fix that handles the example in the statement but not the stated boundary;
- a feature that hard-codes the values of the visible examples;
- a refactor that leaves the structure unchanged (no-op), or restructures but changes behavior.

**Forbidden shortcuts.** Declared per task only when needed, and each MUST be explicit in the public
statement, reasonable, objectively checkable, and motivated by task validity. Each declared shortcut
names its detection mechanism (hidden test, protected-path restore, structural check).
Examples: hard-coding test outputs; editing or deleting public tests to suppress failures (handled
generically by protected-path restore); deleting required functionality; bypassing the stated API.
A prohibition that cannot be checked MUST NOT be written.

**Legitimate alternative vs shortcut.** Any implementation that satisfies the public statement,
passes hidden acceptance and regression, and respects the declared constraints is legitimate, even
if it differs from the reference in structure, naming or approach. A shortcut is a change that makes
checks pass **without** delivering the stated behavior. When in doubt the author extends the
statement, not the hidden checks.

## 10. Refactor tasks — structural criterion

A behavior-preserving refactor starts with behavior already passing, so behavioral tests cannot
distinguish success from doing nothing. Each refactor task needs an **objective structural
criterion** [FROZEN §6: required; exact form O15 OPEN-FINAL] that:

1. is stated in the public task statement in checkable terms;
2. can be checked independently of the agent (AST/compiler-API/import-graph check in the hidden
   evaluator, not regex over formatting where avoidable);
3. **fails on the pristine fixture** and therefore rejects a no-op;
4. passes on the reference **and** on at least one alternative valid solution (§8);
5. constrains only what the statement names (e.g. "logic X lives in exactly one exported function
   in module M and modules A, B, C use it"), not internal shape, naming of private helpers or
   formatting.

Appropriate categories (choose per task): remove a named duplication; extract a named
responsibility into a named module boundary; remove a named deprecated dependency; eliminate a
named coupling (module A must no longer import module B); consolidate duplicated logic into one
shared abstraction.

Not adopted by default: generic metrics such as line count, cyclomatic complexity or maintainability
indices — they are gameable, weakly related to the stated goal, and reward reformatting.

## 11. Task validity gate

Run with the evaluator only, no model call [FROZEN §9]. A package is **gate-passed** only when every
item holds and its evidence is stored.

### 11.1 Bug fix / feature

1. Package metadata complete (§13); all hashes computed.
2. Pristine fixture deterministic: public tests give identical results over **3** consecutive runs
   [PILOT; small N chosen because fixtures are tiny and fully offline — flakiness at N=3 already
   disqualifies].
3. Public test / regression baseline understood: regression suite passes on pristine; any
   pre-existing public failure is explained in the statement.
4. At least one acceptance test fails on pristine **for the intended reason** (§5).
5. Reference solution passes acceptance.
6. Reference solution passes regression.
7. At least one known-wrong solution is rejected (acceptance or regression fail, or integrity
   violation), with the rejecting check recorded.
8. Author review question (§6) answered "yes" for every hidden test.
9. Hidden/reference/evaluator material is outside the working copy and unreachable from the agent
   sandbox (harness canary-style probe on the task's actual layout; `smoke.srt_canary_probe`
   pattern).
10. Task statement bytes frozen; hash recorded.
11. Evaluator determinism: pristine and reference each evaluated **3** times with identical verdicts
    [PILOT; protocol §6 requires determinism, N is the pilot choice].

### 11.2 Refactor

Replace items 4–7 with:

4r. Behavior baseline: acceptance-behavior and regression suites **may** pass on pristine.
5r. The structural criterion (§10) **fails** on pristine.
6r. Reference passes the structural criterion, acceptance behavior and regression.
6r'. At least one alternative valid solution passes the same checks.
7r. A no-op is rejected (structural criterion fails) **and** at least one behavior-changing
    refactor is rejected (acceptance-behavior or regression fails).

### 11.3 Evidence stored and versioned

For each gate execution: task version hash; evaluator version; for every evaluated state
(pristine, reference, alternative, each known-wrong) — per-test results, exit codes, evaluator
stdout/stderr, and the failure message of the intended failing test; the author-review answers;
the canary-probe result; date and harness version. Evidence lives in the results store under the
harness root, never inside the fixture. Evidence is append-only; a re-gate after any change creates
a new record for the new version.

## 12. Pilot → final firewall

[FROZEN F16, §9] Pilot task repositories, statements, hidden tests, known-wrong solutions,
failure modes and reference solutions MUST NOT become, or be adapted into, any of the six final
tasks. Final tasks may reuse the abstract categories (language × bug fix / feature / refactor) but
are independently authored and frozen. [PILOT] Additionally, a final task SHOULD NOT reuse a pilot
task's problem domain (e.g. no final "range formatting" task if a pilot used it), so that knowledge
gained from pilot outputs cannot shape the final task.

## 13. Version identity

A task version is identified by a hash over: statement bytes, fixture tree hash, baseline-commit
metadata, dependency lockfile hash, hidden test files, structural-check files, evaluator
configuration (commands, protected paths, evaluator timeout), the `generated_outputs` ignore
policy (§13a) and reference-solution hash. This hash is the manifest's `task_version_hash`. Any change to any part produces a new version
and requires a new validity gate. Within one pilot series no package changes silently; a change
mid-series is handled by `PILOT_PLAN.md` §14.

### 13a. Generated outputs (package-owned ignore policy)

A package may declare, in `package.json`, the build/runtime outputs that the task's own commands
legitimately create: `"generated_outputs": ["dist/**", "*.tsbuildinfo"]`.

- **Forms.** Only two explicit forms exist, with no gitignore semantics:
  - `<dir>/**` — a plain directory name at the working-copy root;
  - `*.<ext>` — a file-name suffix anywhere.
- **Rejected at load.** The harness refuses anything that could hide a meaningful change:
  - `**`, `*`, exact file names (`package.json`, `tsconfig.json`, `CLAUDE.md`), nested or dotted
    dirs;
  - `src/`, `lib/`, `test(s)/`, `__tests__/`, `spec/`, `.claude/`, `.git/`, `node_modules/`;
  - source/config extensions (`py ts tsx js … json md yaml …`).

  An instruction path (`CLAUDE.md`, `CLAUDE.local.md`, `.claude/**`) is never treated as
  generated, so treatment drift is always detected.
- **Where it applies.** Declared outputs are excluded from the start/final state, `changed_files`
  and `final.diff`. They are **removed from the evaluator copy** before any check, so hidden build
  outputs can never influence a verdict; checks rebuild them from source.
- **Where it does not.** C2 phase 1 stays strict: any new file there is a write
  (`phase1_write`).
- **Pristine and identity.** The pristine fixture must not already contain declared outputs;
  otherwise the gate fails. The list is part of the task version hash and of the evaluator
  identity, so it is identical for C0/C1/C2, and changing it is a new version (the frozen series
  spec then fails closed).

## 14. Harness dependencies of this standard

This standard assumes capabilities the current harness does not yet have (verified in source,
2026-09-27; full list and ownership in `PILOT_PLAN.md` §15): a test-running evaluator with
protected-path restore, hidden-test injection, integrity detection and structural-check hook (G5);
a single-commit git baseline in the working copy (G6); preservation of the final working-copy state
or diff for re-evaluation (G7); and a treatment-file injection path that does not trip the
ancestor-instruction preflight (G9). Until those exist, no pilot package can pass §11 end-to-end.

## 15. Package checklist

- [ ] Statement written; bad-pattern checklist (§3) clean; forbidden shortcuts explicit and checkable
- [ ] Fixture small, synthetic, pinned deps, offline, single neutral commit, README with test command
- [ ] No hidden/reference/evaluator/experiment-hinting names in the fixture
- [ ] Acceptance tests mapped to statement sentences
- [ ] Regression suite passes on pristine
- [ ] Hidden tests pass the author review question
- [ ] Protected-path list and ignore list written
- [ ] Reference solution (+ alternative for refactor) passes
- [ ] ≥1 known-wrong solution rejected (refactor: no-op and behavior-breaking both rejected)
- [ ] Refactor only: structural criterion stated publicly, fails on pristine
- [ ] Determinism: 3× pristine, 3× reference identical
- [ ] Canary probe on the task layout passes
- [ ] Task version hash computed; evidence stored
