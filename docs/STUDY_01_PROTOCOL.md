# CodeAgent ConfigLab — Study 01 Protocol

Status: **DRAFT — NOT FROZEN** (drafted 2026-10-09; revised 2026-10-09 to apply operator /
Evaluation-Architect decisions R1–R8; final pre-approval patch P1–P6 on 2026-10-09). This is a research-protocol draft for operator review. It
does not freeze any decision, define any final task package, generate any schedule or authorize
any run. Nothing in it is binding until an explicit operator freeze records it, with hashes, as
described in §7. §10 gives the order of the remaining gates.

| Revision decision | Applied in |
|---|---|
| R1 Task success = existing `resolved` on a countable observation | §4.1, §4.2 |
| R2 Agent-time metric source | §4.1, §4.2 |
| R3 Two primary contrasts; C2 vs C0 descriptive only | §2 |
| R4 Intended replacement / re-evaluation adoption | §6.1, §6.3 |
| R5 Final-series harness blocker | §9 |
| R6 TypeScript refactor candidate replaced | §5.1, §5.7 |
| R7 Open decisions kept open | §6.2 |
| R8 Next-gate order | §10 |
| P1 Separate `harness_git_sha`, `study_snapshot_hash` and `study_freeze_commit` | §6.2, §7 |
| P2 Primary results use the planned-cell denominator | §4.2, §8 |
| P3 Python refactor candidate replaced | §5.1, §5.4 |
| P4 Blocker tied to the protocol-draft baseline commit | §9.1 |
| P5 Stricter pre-freeze treatment-change rule | §6.2 (S3) |
| P6 Consistent freeze / gate wording | §7, §10 |

**Precedence.** `docs/EXPERIMENT_PROTOCOL_V0.md`, with amendments A1 and A2, is the authoritative
experimental contract. Its rules on validity, replacement, re-evaluation, clean runs, sandboxing,
C2 and the information boundary apply to Study 01 unchanged, together with the rules in
`docs/PILOT_TASK_STANDARD.md`, `docs/RUN_MANIFEST_V0.md`, `docs/PILOT_SERIES_V0.md` and
`docs/PILOT_PLAN.md`. This document points to those rules and does not restate them. It only adds
decisions that are specific to Study 01. If this document ever conflicts with them, the existing
rule wins until a versioned protocol amendment says otherwise. This document never relaxes an
existing rule.

Tags:

| Tag | Meaning |
|---|---|
| **[INHERITED]** | Already fixed by an existing document; the pointer is given and the rule is not restated |
| **[STUDY-01 DRAFT]** | Proposed here for Study 01; binding only after operator freeze |
| **[OPEN — OPERATOR FREEZE]** | Undecided; must be decided and recorded before the first final run |
| **[CANDIDATE]** | Design material for discussion; not a task specification |

---

## 1. Scope

[STUDY-01 DRAFT] Intended design. It matches protocol F1 [INHERITED].

| Item | Value |
|---|---|
| Languages | Python, TypeScript |
| Task types per language | one bug fix, one small feature, one behavior-preserving refactor |
| Final tasks | 6 |
| Configurations | C0, C1, C2 (protocol §3.2) |
| Repetitions | 3 independent repetitions per task × configuration (protocol §2) |
| Planned cells | 6 × 3 × 3 = **54** |
| Pilot tasks | `P-PY-01` and `P-TS-01` are **excluded** from the final dataset and from every aggregate (protocol §9, F16; `PILOT_V1_CLOSEOUT.md` §1) |

**54 cells are not 54 independent tasks.** Study 01 has **six task units**. The three repetitions
of a task × configuration pair re-run the same task under the same configuration. They estimate
within-task execution variability (model sampling is nondeterministic and cannot be seeded through
the CLI; protocol §2). They do not add new tasks. Every result is reported per task first
(protocol §1: tasks are the dominant source of variance).

Reporting units are kept apart exactly as in `RUN_MANIFEST_V0.md` "Reporting units": planned cells,
attempts, countable observations, external interruptions and invalid attempts [INHERITED].

## 2. Pre-specified research questions

[STUDY-01 DRAFT] Study 01 has **exactly two primary contrasts**:

| ID | Contrast | Question |
|---|---|---|
| **RQ1** | C1 vs C0 | On this exact six-task set, what is the effect of the specific frozen repository `CLAUDE.md` treatment relative to the baseline? |
| **RQ2** | C2 vs C1 | With the same `CLAUDE.md`, what is the incremental effect of the defined explicit planning workflow? The workflow is: a read-only phase 1; the frozen planning wrapper around the unmodified task statement; the fixed continuation (approval) message; a phase 2 that continues the same session; and one shared total agent-time budget across both phases (protocol §8, F5) |

**C2 vs C0** is kept only as the **descriptive combined-treatment contrast** that the base
protocol already recognizes (protocol §1: "the combined effect of both"). It is reported as a
labelled descriptive row. It is **not** a third primary research question, and no claim is
organized around it. [R3]

C2 is always the explicit planning workflow, never a benchmark of the built-in Plan Mode (F4).

## 3. Interpretation boundaries

[INHERITED] Everything protocol §1 says V0 "cannot show" applies.

[STUDY-01 DRAFT] In addition, Study 01 results **must not** be reported as supporting any of these
conclusions:

- that CLAUDE.md files in general improve coding (RQ1 concerns one specific frozen file);
- that planning is generally superior (RQ2 concerns one specific workflow under one budget);
- that Python benefits more than TypeScript;
- that refactors benefit more than bug fixes, or any other ranking of task types.

Why: each language × task-type combination has exactly **one** task. Any language or task-type
pattern is therefore fully confounded with the identity of that single task. Such patterns may be
described only as **exploratory hypotheses for later work** and must be labelled that way.

## 4. Outcome definitions

### 4.1 Metric table

| Tier | Metric | Definition | Source / rule |
|---|---|---|---|
| **Primary** | `task_success` | The **existing `resolved` task outcome**, evaluated for a **countable observation** (`analysis_eligibility.status = countable`, derived by `status.derive_analysis_eligibility` [INHERITED, G3/G8]). [R1] | `resolved` as already defined (protocol §6, `RUN_MANIFEST_V0.md`, `status.is_resolved`): `valid` ∧ acceptance `pass` ∧ regression `pass` ∧ integrity `clean`. This **includes the existing integrity requirement** (F13). Task-required structural checks are part of the acceptance axis (G5). **No second success rule is defined.** |
| Secondary | Total agent elapsed time | Agent wall-clock: the time the agent process(es) of the attempt were running (`PILOT_PLAN.md` §9). **C0/C1:** the agent-process elapsed evidence of the single invocation. **C2:** phase-1 agent elapsed + phase-2 agent elapsed, under the one shared deadline (protocol §8, F5; closeout §2). The inter-phase harness gap is not charged. [R2] | **Intended source, fixed at protocol level:** C0/C1 → `process.json`; C2 → `c2.json` (per-phase records). **Excluded:** evaluator time, cleanup time, and lifecycle steps around the agent (prepare, preflight, capture, finalization). `result.duration_seconds` is **not** agent-performance time, because lifecycle, preflight, evaluation and finalization all contribute to it. See the field-binding note in §4.2. |
| Secondary | Changed source-file count | Number of added, modified, deleted and renamed files inside the task's frozen **source scope** (§6.2, open). | `changed_files.json`, which is computed relative to the agent start state, so treatment-injected material (`CLAUDE.md`, the Candidate-2 `.claude` seeds) is never counted [INHERITED, G7/G9]. Declared `generated_outputs` and built-in caches are excluded (`PILOT_TASK_STANDARD.md` §13a) [INHERITED]. |
| Secondary | Diff size | Added + deleted lines in `final.diff`, restricted to the same source scope. | Same exclusion policy as above. A withheld diff (`final_diff_withheld`, G12) is reported as **withheld**, never as 0. |
| Secondary | Failure category | Descriptive category for each countable observation that did not succeed: `timeout`; `error_exit`; integrity `protected_path_modified` / `out_of_tree_write_detected`; acceptance `fail` (structural vs behavioral named where the evaluator record separates them); regression `fail`. | Derived only from status axes and `evaluator.json` that are already recorded. It is a reporting label, **not** a new status value. When several apply, all are listed, not ranked. |

### 4.2 Rules for these metrics

**Three separate questions.** [R1] These are kept conceptually separate. None is derived from task
success, and none is merged into a combined status:

| Concept | Question it answers | Source |
|---|---|---|
| Run validity (`run_validity`) | Was the attempt executed as specified? | Protocol §6/§10; classified from agent-phase evidence before scoring (F12) |
| Analysis eligibility (`analysis_eligibility`) | Does this attempt count as the planned observation for its cell? | `status.derive_analysis_eligibility(run_validity, agent_outcome)` (G3/G8) |
| Task success (`task_success`) | Given a countable observation, did it resolve the task? | Existing `resolved` (protocol §6) |

**Agent-time field binding.** [R2] The protocol fixes the **authoritative artifact and the
semantic definition** given in §4.1. It does not fix a field name. For orientation only, current
source emits:
- an `elapsed_seconds` value in the process metadata written to `process.json`, measured around
  the agent process by `process_control.run_with_deadline`;
- per-phase entries in `c2.json` that contain the same process metadata as well as a per-phase
  duration, plus an inter-phase gap value.

These names are not yet documented as a stable contract. The exact field binding is confirmed at
freeze (§6.2). The preferred binding is the same kind of agent-process elapsed evidence for C0, C1
and both C2 phases, so that the configurations are measured the same way.

- **Validity is not success.** Technical run validity (`run_validity`) and countability
  (`analysis_eligibility`) are separate axes from task success [INHERITED, protocol §6, G3].
- **Non-countable attempts are never converted into task failures.** Invalid attempts, external
  interruptions (`limit_interrupted`) and `evaluation_pending` attempts appear in their own rows.
  A cell that never gets a countable attempt is reported as missing (`no_valid_attempt`) and is
  never imputed [INHERITED, protocol §10, `PILOT_SERIES_V0.md`]. In primary presentation, such
  cells stay in the **planned-cell denominator** as "no countable observation" (§8, P2).
- **A valid timeout is countable.** Its final state is evaluated under the existing rules, and the
  `agent_outcome` is reported next to the verdict [INHERITED, `RUN_MANIFEST_V0.md` "Timeout
  semantics"].
- **Conditional timing.** A timing summary over successful observations only is a *conditional*
  analysis. It is always shown next to the counts of failures, timeouts and non-countable attempts
  in the same task × configuration. It must never be the only timing view, and it must never hide
  that a configuration failed or timed out more often.
- **C2 timing covers both phases.** C2 agent time is always the phase-1 + phase-2 total. A
  phase-2-only figure may appear only as a labelled breakdown.

### 4.3 Deferred / exploratory (not formal Study 01 metrics)

| Item | Status | Reason |
|---|---|---|
| Token / usage fields | Deferred | Cannot become formal until it is verified whether a resumed C2 invocation reports per-invocation or cumulative session values (`PILOT_PLAN.md` §12, protocol O8). Raw events stay preserved. **Missing usage is never zero.** `total_cost_usd` is not a billed amount under Pro. |
| Unnecessary-change judgment | Deferred | No frozen rubric exists. Inclusion is an open decision (§6.2). |
| Generic quality proxies (complexity, maintainability indices, line counts as quality) | Not adopted | Gameable and weakly tied to the stated task (`PILOT_TASK_STANDARD.md` §10). |
| Across-repeat consistency claims | Exploratory only | Three repetitions per pair can show the spread. They cannot support claims about consistency as a property of a configuration. |

**No weighted composite score** is defined [INHERITED, F11].

## 5. Candidate six-task design matrix — [CANDIDATE], NOT FROZEN

These are task **concepts** for discussion. None is implemented. None has a fixture, statement,
hidden test, reference solution or gate. All final tasks are authored independently under
`PILOT_TASK_STANDARD.md` (pilot→final firewall, §12) and must pass its validity gate (§11) before
any freeze. Contract outlines describe **observable behavior only**. Several implementations must
be able to satisfy each of them, and none implies an expected implementation. Any boundary or
tie-break rule that a hidden test relies on **must** appear in the public statement or in the
repository's existing contract. That is the author-review question of `PILOT_TASK_STANDARD.md` §6.

### 5.1 Summary

| ID | Lang | Type | Problem (one line) |
|---|---|---|---|
| F-PY-BUG-01 | Python | bug fix | Header replacement in a small HTTP-style header container mishandles case-insensitive names and duplicates |
| F-PY-FEAT-01 | Python | feature | Add time-window filtering to an existing in-memory event-query API |
| F-PY-REF-01 | Python | refactor | Split a monolithic configuration loader into separated parsing/coercion, defaulting/normalization and validation stages, without changing behavior |
| F-TS-BUG-01 | TypeScript | bug fix | A build-order resolver drops declared nodes that have no dependency edges |
| F-TS-FEAT-01 | TypeScript | feature | Add aliases to an existing command registry, with defined collision semantics |
| F-TS-REF-01 | TypeScript | refactor | Replace a command processor's monolithic branch/switch dispatch with a handler-registry structure, without changing behavior |

### 5.2 F-PY-BUG-01 — case-insensitive header replacement / duplicate handling

- **Problem.** A small header-collection class documents that header names are case-insensitive.
  Its "set/replace" operation removes only entries whose name matches exactly. Setting
  `content-type` when `Content-Type` already exists therefore leaves both, and lookups return
  inconsistent values.
- **Public contract outline.** Names compare case-insensitively. Replacing a header removes
  **every** existing entry with that name, whatever its case or count, and leaves exactly one
  entry with the new value. The statement must say which name spelling is kept after a replace
  (the existing docstring or the statement fixes this). Appending a value, as opposed to
  replacing, still allows multiple values. Iteration order of the *other* headers is unchanged.
- **Preserved behavior.** Append semantics for multi-valued headers; lookup of headers that were
  never replaced; iteration order of untouched entries; the existing public method signatures.
- **Hidden-test justification.** Replace over several pre-existing case variants; replace when the
  name is absent; replace followed by lookup in a different case; untouched headers keep their
  order. Each follows from "case-insensitive" plus "replace leaves exactly one entry", both of
  which are public.
- **Reference-solution role.** Proves solvability and validates the suites. It is not a template:
  a normalized-key index and a filter-then-append fix must both pass.
- **Known-wrong classes.** Removes only the first case-insensitive match (duplicates survive);
  lower-cases every stored name globally, which breaks the documented spelling-preservation rule;
  fixes `replace` by also collapsing appended multi-values (regression fail).
- **Structural criterion.** Not applicable (bug fix).

### 5.3 F-PY-FEAT-01 — event-query time-window filtering

- **Problem.** An in-memory event store has a query API that filters by type and field values.
  Users need to restrict results to a time window.
- **Public contract outline.** New optional `start` / `end` parameters on the existing query
  entry point. The statement must state explicitly: the inclusivity of each bound (for example
  start-inclusive and end-exclusive); that an omitted bound means unbounded; how a window with
  `start > end` behaves (an empty result or a named error, whichever the statement chooses); that
  the window combines with the existing filters as a conjunction; and that the existing result
  ordering is kept. Timestamp type and timezone handling follow the store's existing documented
  timestamp contract.
- **Preserved behavior.** Every existing query without a window returns exactly what it did
  before. Existing filters, ordering and the return type are unchanged.
- **Hidden-test justification.** Events exactly on each bound; one-sided windows; window combined
  with an existing filter; empty window; ordering kept. All follow from the stated bound semantics
  and the existing ordering contract.
- **Reference-solution role.** Proves solvability. Filtering before or after the existing filters,
  or index-based versus linear scan, must all be accepted.
- **Known-wrong classes.** Wrong inclusivity on one bound (passes the statement's interior
  example, fails at the boundary); a window that replaces the existing filters instead of
  combining with them; values hard-coded from the statement's examples.
- **Structural criterion.** Not applicable (feature).

### 5.4 F-PY-REF-01 — behavior-preserving configuration-loading pipeline refactor [P3]

Replaces the earlier sync/async retry-decision consolidation candidate. That candidate was not
invalid. It was removed because its structural pattern (duplicated logic → one shared entity →
several consumers) is too close to pilot `P-TS-01`'s refactor pattern. This candidate uses a
different refactor category: *extract named responsibilities* out of one function into separate
stages (`PILOT_TASK_STANDARD.md` §10).

- **Problem.** A small Python configuration module exposes one public configuration-loading entry
  point. One large function currently performs several responsibilities inline: parsing and
  coercion of raw values, default handling and normalization, and validation. The refactor must
  separate these responsibilities into a clear staged pipeline while public behavior stays the
  same.
- **Public contract outline.** "The loader is restructured into separated, named
  responsibilities/stages (as named in the statement, for example parsing/coercion,
  defaulting/normalization and validation), and the public loader composes or delegates through
  them. Preserved unchanged: the public loader signature; the accepted input forms; the produced
  configuration values; default behavior; normalization and coercion semantics; the validation
  error type; the validation error message where it is currently part of the contract; and
  ordering/precedence semantics wherever they are observable." The statement names the stages
  only as far as the structural criterion needs. It does **not** force one private
  implementation, class layout or file split. Stages may be functions, methods or small objects,
  in one module or several.
- **Preserved behavior.** Every value produced for valid input; every default for an omitted
  value; the coercion and normalization results at their boundaries; the error type (and the
  message where contractual) for every invalid input; the outcome when fields interact or
  precedence rules apply (for example which source or field wins, and which error is reported
  first when several fields are invalid, if that is observable today).
- **Hidden-test justification.** Hidden tests use **only the public loader**. Where the eventual
  fixture supports them, they cover:
  - valid values;
  - omitted/defaulted values;
  - coercion/normalization boundaries;
  - invalid values;
  - interacting fields and precedence rules;
  - the exact existing error behavior where it is public.

  "Behavior unchanged" is the public requirement. Every hidden case must be justified by the public
  statement or by the repository's existing contract (docstrings, README, public tests;
  `PILOT_TASK_STANDARD.md` §6).
- **Reference-solution role.** Proves solvability and evaluator correctness, not a preferred
  implementation. At least one **alternative valid implementation with a different private
  organization** (for example free functions vs a small pipeline object, or a different stage
  split within the named responsibilities) is required to pass (`PILOT_TASK_STANDARD.md` §8, §10).
- **Known-wrong classes.**
  - No-op: the original monolithic loader remains.
  - Cosmetic extraction: stage wrappers exist, but the old function still performs the substantive
    parsing/defaulting/validation work.
  - Incorrect stage ordering that changes precedence or error behavior (for example validating
    before defaults are applied).
  - An extraction that accidentally changes defaults, coercion or validation (regression fail).
  - Duplicated validation that remains both in the new pipeline and in the old loader.
- **Structural criterion.** A Python AST-based check, stated publicly in checkable terms, that
  establishes at least:
  - the required separated responsibilities/stages exist as named;
  - the public loader composes or delegates through them;
  - the original monolithic implementation is no longer authoritative for all stages, meaning the
    substantive logic of each named responsibility is no longer in the loader body.

  The check must fail on pristine, on the no-op and on the cosmetic-wrapper variant. It must pass
  on the reference and on at least one structurally different valid alternative. It does not
  constrain private naming, class layout or file split beyond the publicly named structural
  objective.
- **Residual risk (recorded).** Static analysis of "which function performs which responsibility"
  has limits. Examples: stage logic re-inlined under a helper with a different name; dynamic
  dispatch between stages; validation duplicated in a way that only partly overlaps. The author
  must define the AST check precisely, validate it against the cosmetic-extraction and
  duplicated-validation known-wrong variants, and review it in each diff, as recorded for
  F-TS-REF-01.

### 5.5 F-TS-BUG-01 — build-order resolver preserving isolated declared nodes

- **Problem.** A resolver takes a set of declared build targets and their dependency edges and
  returns a valid build order. Targets that are declared but have no edges in either direction are
  missing from the output.
- **Public contract outline.** The output contains **every declared node exactly once**. Every
  dependency comes before its dependents. Cycle detection keeps its existing error behavior. The
  statement must state the tie-break rule for nodes with no ordering constraint between them (for
  example declaration order). If it does not, hidden tests may only check order validity, not one
  particular order.
- **Preserved behavior.** Orders for graphs where every node has an edge; cycle errors; the
  public types and function signature.
- **Hidden-test justification.** Isolated nodes alone; isolated nodes mixed with chains; a graph
  with only isolated nodes; the empty input; the existing cycle cases. All follow from "every
  declared node exactly once".
- **Reference-solution role.** Proves solvability. Seeding with all declared nodes and appending
  missing nodes afterwards are both valid if the stated tie-break rule is kept.
- **Known-wrong classes.** Appends isolated nodes but duplicates nodes that also appear in edges;
  includes isolated nodes only when no edges exist at all; breaks the stated tie-break rule.
- **Structural criterion.** Not applicable (bug fix).

### 5.6 F-TS-FEAT-01 — command-registry aliases with collision semantics

- **Problem.** A command registry maps command names to handlers. Users need aliases (alternative
  names that resolve to a registered command).
- **Public contract outline.** A way to register aliases for a command, either at registration
  time or afterwards (the statement fixes which). Lookup by alias resolves to the canonical
  command. Listing returns canonical commands only, unless the statement says otherwise. The
  statement must state the **collision semantics**: what happens when an alias equals an existing
  command name, an existing alias, or itself (for example a named error type), and whether a later
  command registration may take over an alias.
- **Preserved behavior.** Registration and lookup by canonical name; the existing duplicate-name
  error; listing order; public types.
- **Hidden-test justification.** Each stated collision case; alias lookup; listing excludes
  aliases; existing duplicate-name behavior unchanged. Every case is one of the stated collision
  rules.
- **Reference-solution role.** Proves solvability. A separate alias map and a unified name table
  with a canonical flag must both pass.
- **Known-wrong classes.** An alias silently shadows (overwrites) a canonical command; aliases
  leak into the listing; the collision check is enforced at registration but not when aliases are
  added afterwards.
- **Structural criterion.** Not applicable (feature).

### 5.7 F-TS-REF-01 — behavior-preserving command-dispatch refactor [R6]

Replaces the earlier diagnostics / shared-normalization candidate. That candidate was removed
because it had the same structure as pilot `P-TS-01`: consolidating normalization logic that was
duplicated across output modules (`PILOT_TASK_STANDARD.md` §12, `PILOT_PLAN.md` §17). Command
dispatch is not a pilot problem domain, and the refactor category here is different (*extract a
named responsibility into a named module boundary*, `PILOT_TASK_STANDARD.md` §10, rather than
*consolidate duplicated logic*).

- **Problem.** A small command processor exposes one public entry point that takes a command
  (identifier + arguments) and returns a result or raises a defined error. Internally, it selects
  behavior through one monolithic branch/`switch` over the command identifier, with each
  command's behavior written inline in its branch. Adding or changing a command means editing that
  one function.
- **Public contract outline.** "Dispatch goes through a handler-registry structure: a named
  registry in a named module maps each command identifier to its handler, and the public entry
  point selects the handler by looking it up there. The old monolithic branch/switch over command
  identifiers no longer decides dispatch. The public command API (entry-point signature, command
  identifiers, argument shapes, result types) is unchanged. Every command's output, every error
  (type and message) and the order of observable effects are unchanged, including the behavior for
  unknown commands. Command-specific behavior stays local to that command's handler." How handlers
  are written and registered (a map literal, registration calls, one function or class per handler,
  one file or several) is **not** prescribed beyond the names the statement fixes.
- **Preserved behavior.** The result of every existing command for valid arguments; argument
  validation errors per command; the unknown-command error and any default/fallback behavior; the
  order of observable effects for commands with several steps (for example the order of emitted
  events or log records, if the fixture exposes them publicly); the public types and the entry-point
  signature.
- **Hidden-test justification.** Hidden tests call **only the public entry point** and cover every
  command, every documented error path, unknown commands and effect order. "All outputs, errors and
  order semantics unchanged" is the public requirement, so any input within the declared API is a
  fair test. No hidden test inspects handler names, file layout or registration style. The
  structural check covers only the named registry and the dispatch path.
- **Reference-solution role.** Proves solvability and validates the suites. It is one of several
  valid structures. An **alternative valid solution** with a different registration style (for
  example a map literal vs explicit registration calls) is required (`PILOT_TASK_STANDARD.md` §8,
  §10), so that the evaluator does not overfit to the reference.
- **Known-wrong classes.**
  - No-op: the monolithic switch stays.
  - Decorative registry: a registry is added, but the switch still decides dispatch, so the
    registry is dead code or only a fallback.
  - Pass-through registry: every registry entry calls back into the old switch, so the switch
    stays authoritative.
  - Changed unknown-command or default behavior: for example a different error type/message, or a
    silent no-op where an error used to be raised.
  - Changed effect order, or command-specific behavior moved into shared code so that one command's
    result changes (regression fail).
- **Structural criterion.** A TypeScript compiler-API check, stated publicly in checkable terms:
  - the named registry exists in the named module and maps command identifiers to handlers;
  - the public entry point selects the handler through that registry;
  - no branch/`switch` over the command identifier remains in the dispatch path from the entry
    point to the handler, whether in the entry point itself or in anything the registry delegates
    back to;
  - every public command identifier resolves through the registry.

  The check fails on pristine, on the no-op and on the decorative and pass-through variants. It
  passes on the reference and on the alternative solution. It does not constrain handler naming,
  file split or registration style beyond what the statement names.
- **Residual risk (recorded).** Static analysis of "dispatch path" has limits, for example an
  if-chain that has been re-hidden behind a helper with a different name. The author must define
  the dispatch-path check precisely, validate it against both the decorative and the pass-through
  known-wrong variants, and review it in each diff, as with `P-TS-01`'s recorded residual risk.

## 6. Carry-forward decisions vs open decisions

### 6.1 Inherited / binding from existing protocol

These are reused by reference. Study 01 neither re-specifies nor changes them.

| Decision | Source |
|---|---|
| Treatment definitions C0 / C1 / C2; only intended treatment differences; byte-identical task statement; uncommitted treatment file on a neutral baseline; treatment-state invariant | Protocol §3, F3–F6; Amendment A2; G11 loader (`RUN_MANIFEST_V0.md`) |
| Identical implementation envelope (C0 = C1 = C2 phase 2) | Protocol §3.1, F5 |
| Information boundary (what the agent may and must not see) and the credential execution boundary | Protocol §5, F9; Amendment A1 |
| Clean-run contract (fresh working copy, opaque path, no carryover, real cleanup + residue verification) | Protocol §4, F7–F8; `V1_STATUS.md` |
| Task validity concept and gate (acceptance fails on pristine for the intended reason; regression passes on both; refactor structural criterion; known-wrong rejection; determinism) | Protocol §6; `PILOT_TASK_STANDARD.md` §5–§11 |
| Run validity vs analysis eligibility | Protocol §6/§10; `RUN_MANIFEST_V0.md` (G3, G8); `status.derive_analysis_eligibility` |
| Replacement / re-evaluation policy: **intended adoption** of the pilot-validated policy; formal adoption remains a freeze item | `PILOT_SERIES_V0.md`; `PILOT_PLAN.md` §10–§11; protocol §10 constraints. See §6.3 and §6.2 |
| No outcome-quality reruns | Protocol §10; F12 |
| Shared C2 deadline (one budget for phase 1 + phase 2, phase 2 gets the remainder, gap not charged) | Protocol §8, F5; `PILOT_PLAN.md` §9; `PILOT_V1_CLOSEOUT.md` §2 |
| Same-session continuation with the fixed approval message | Protocol §8; G2; `PILOT_V1_CLOSEOUT.md` §5 |
| Pilot exclusion from the final dataset; FINAL namespace separation | Protocol §9, F16; `PILOT_SERIES_V0.md` "Namespaces" |
| Claude Pro-only cost boundary; `limit_interrupted` never continued under another billing mechanism | Protocol F2, F18, §10 |
| Blocked-by-repetition, seeded, non-adaptive run order | Protocol §11, F17 |
| No weighted composite score; descriptive per-task reporting | Protocol F11, F19 |

### 6.2 Study-01 decisions that still require an explicit operator freeze

**None of these is frozen.** [R7] Each row stays [OPEN — OPERATOR FREEZE] until it is recorded in
the Study-01 freeze material and covered by `study_snapshot_hash` (§7). Pilot values are shown as **reference points only**; showing
them does not adopt them.

| # | Open decision | Notes / reference point |
|---|---|---|
| S1 | Exact six final task packages | From the §5 candidates or replacements; each fully authored and gate-passed under `PILOT_TASK_STANDARD.md` §11 |
| S2 | Source scopes for the changed-file / diff metrics | Per task: which paths count as "source" for §4 (for example `src/**`, excluding public tests); frozen with the task |
| S3 | Exact treatment identities (`CLAUDE.md`, planning wrapper, approval message) | Reference: pilot-v1 hashes (`PILOT_PLAN.md` §8.3). Whether Study 01 reuses the exact pilot treatment bytes is **not decided here**. [P5] **Any treatment change before Study-01 freeze must be justified independently of observed configuration outcomes, versioned, and explicitly operator-approved before final execution.** Treatment tuning in response to observed C0/C1/C2 outcomes remains prohibited (`PILOT_PLAN.md` §14; protocol §3.2). Includes O14 (one file vs per-language variant) |
| S4 | Requested model | Reference: pilot `claude-sonnet-5` (closeout §2); protocol O5 |
| S5 | Effort | Reference: pilot `high` (closeout §2) |
| S6 | Timeout | Reference: pilot `900` s, shared across both C2 phases (closeout §2); protocol O12 |
| S7 | Final harness implementation Git SHA (`harness_git_sha`) | The commit that contains the validated harness implementation. Known only after gates 2–3 of §10; recorded inside the freeze material (§7.1) |
| S8 | Task / evaluator identities | `task_version_hash` per task; evaluator identity including the evaluator-sandbox policy identity |
| S9 | Final seed / run order | Seed text, the optional "no same task consecutively" constraint (O16), and the generated final 54-entry schedule (protocol §11), which is generated at gate 6 and covered by the snapshot |
| S10 | Token / usage inclusion | Depends on O8 verification (§4.3); missing values are never zero |
| S11 | Unnecessary-change rubric inclusion | No rubric exists yet (§4.3) |

Further items that must be confirmed at freeze. Their direction is decided in this draft, but they
are still not frozen:

| # | Freeze confirmation | Direction already decided |
|---|---|---|
| C-a | Formal adoption of the replacement / re-evaluation policy for FINAL runs | Intended adoption in §6.3 (protocol O13 is formally still open for final runs) |
| C-b | Exact agent-time field binding in `process.json` / `c2.json` | Artifact and semantics fixed in §4.1 / §4.2 |
| C-c | Results presentation plan | Draft in §8 |

### 6.3 Intended replacement / re-evaluation adoption [R4]

Study 01 intends to **adopt the pilot-validated replacement and re-evaluation policy**. It does not
invent a new retry scheme. The policy remains an explicit final freeze item (§6.2, C-a), because
the legacy protocol's O13 is formally open for final runs.

Intended adoption:

| Attempt record | Intended handling |
|---|---|
| Countable result, including acceptance/regression failure, valid `timeout` and `error_exit` | **No replacement**. The cell is complete |
| `not_countable:evaluation_pending` | **Evaluator re-evaluation** on the preserved final working copy. **Never an agent rerun** |
| The existing eligible infrastructure, harness and external-interruption categories | **Operator-approved replacement**, never automatic |
| Hard safety violations (the existing halt classes) | **Keep their existing halt semantics** (series halt for review; no plain replacement) |

- At most **one replacement per cell**. If the replacement is also non-countable, the cell is
  reported as `no_valid_attempt` and is never imputed.
- **No outcome-quality reruns.** A replacement decision never looks at evaluator verdicts.
- Every attempt is kept. A replacement is another attempt for the same cell, never an extra
  observation.

The underlying eligibility taxonomy is **not redefined here**. Which validity classes are
eligible, need operator confirmation, halt the series or are not eligible is exactly what the
existing series policy says: the table in `PILOT_SERIES_V0.md` "Replacement vs re-evaluation",
implemented by `series.replacement_decision`, and `PILOT_PLAN.md` §10–§11.

## 7. Study freeze and provenance

### 7.1 Three distinct provenance identities [P1]

Study 01 uses three provenance identities. They are kept separate on purpose, because merging
them would make the freeze refer to itself.

| Identity | What it is | When it is known | Where it is recorded |
|---|---|---|---|
| **`harness_git_sha`** | The exact Git commit that contains the validated harness implementation used for Study 01. It identifies executable harness behavior | After the final-series implementation (gate 2) and the backward-compatibility gate (gate 3) | Inside the Study-01 freeze material, and therefore covered by `study_snapshot_hash`. It **must not change** during Study 01 execution |
| **`study_snapshot_hash`** | One deterministic, canonical hash over the frozen Study-01 experimental inputs and identities (§7.2) | When the freeze material is complete (gate 6) | With the freeze material, as its identity |
| **`study_freeze_commit`** | The Git commit created **after** the frozen protocol, snapshot and schedule artifacts have been written and committed. External provenance for the frozen study state | After that commit exists (end of gate 6) | **Only outside** the content it identifies: external audit metadata, a later closeout/status record, release metadata, or another non-self-referential provenance record |

**No self-reference.** Dependencies run in one direction only:
`harness_git_sha` → freeze material → `study_snapshot_hash` → `study_freeze_commit`.
`study_freeze_commit` is **never** an input to `study_snapshot_hash`, and it is never embedded in
any content that would have to contain its own commit SHA. `harness_git_sha` names an *earlier*
commit, so recording it inside the freeze material creates no cycle.

### 7.2 Snapshot coverage

[STUDY-01 DRAFT] Before the **first** final run, the freeze material must cover at least:

- the protocol version and hash (this document as frozen, plus the `EXPERIMENT_PROTOCOL_V0.md`
  version and the amendments in force);
- `harness_git_sha`;
- the six task package identities (`task_version_hash` per task);
- the evaluator identities (per task, including the evaluator-sandbox policy identity);
- the treatment identities (`CLAUDE.md`, planning wrapper and approval message hashes);
- the requested model;
- the effort;
- the timeout;
- the replacement-policy adoption (§6.3; C-a);
- the agent-time binding (§4.2; C-b);
- the run-order seed;
- the generated final schedule;
- every other explicit Study-01 freeze decision this protocol requires (§6.2, including S2, S10,
  S11 and C-c).

**Semantic requirement only:** the freeze artifact has **one deterministic snapshot identity**,
`study_snapshot_hash`. Equal frozen inputs give an equal hash, and any change to a covered input
gives a different hash. This document does not define the serialization. For orientation only:
the repository already derives the pilot `spec_hash` and `schedule_hash` with a canonical-JSON
hash (`hashing.canonical_json_hash`). The concrete snapshot mechanism is decided and implemented
outside this documentation task.

### 7.3 Rules once Study 01 execution begins

- Task, treatment, budget and harness behavior are **not changed in response to results**.
- If a genuine infrastructure defect is discovered, **all evidence is preserved** and the existing
  validity and replacement rules apply (protocol §10; `PILOT_SERIES_V0.md`). The fix is recorded
  as a versioned amendment. A change that affects comparability starts a new study version, and
  runs from different versions are not pooled (protocol §9; `PILOT_PLAN.md` §11, §14). A harness
  fix produces a new `harness_git_sha`, and therefore a new `study_snapshot_hash`. Runs under it
  do not belong to the frozen Study 01 snapshot.
- The harness is **not silently patched** with execution continuing as though nothing changed.
  The pilot ran under an evolving harness without per-attempt source hashes
  (`PILOT_V1_CLOSEOUT.md` §4.3). That is acceptable for a machinery pilot and not acceptable for
  Study 01.

The freeze material and `study_snapshot_hash` are produced only at gate 6 of §10, after gates 1–5.
In particular, the commit named by `harness_git_sha` must already contain the final-series harness
support (§9.1) that passed the gate-3 regression / backward-compatibility gate.

## 8. Analysis presentation plan — draft, not executed

[STUDY-01 DRAFT] Minimal presentation, in this order:

1. **Task-by-task success table first.** Rows: six tasks. Columns: C0 / C1 / C2. [P2] The
   denominator is the **frozen planned-cell count**, normally 3 per task × configuration. Each
   entry shows all four parts:

   `R resolved · F failed · M no countable observation / N planned`

   For example `2 resolved · 0 failed · 1 no countable observation / 3 planned`. The parts always
   satisfy R + F + M = N.
   - R: countable observations with `task_success` (= `resolved`).
   - F: countable observations without it.
   - M: planned cells that have no countable observation (`no_valid_attempt`, or not yet
     observable).
   - N: planned cells.

   **Replacement attempts are attempt accounting. They never increase N.**
   Next to the primary table, a separate **accounting table** per task × configuration reports:
   - attempts (originals + replacements);
   - replacements;
   - non-countable attempts by class (`not_countable:invalid` by `run_validity`,
     `not_countable:external_interruption`, `not_countable:evaluation_pending`);
   - cells without a countable observation.

   These counts are never folded into R or F.
2. **C0 / C1 / C2 aggregate descriptive summary second.** Totals across tasks per configuration
   use the **same planned-cell denominator**: 18 planned cells per configuration and 54 overall,
   shown as R · F · M / N. The per-task breakdown stays visible. The denominator is never silently
   changed from planned cells to countable observations only. A rate over countable observations
   may appear only as a **labelled conditional view** next to the planned-denominator view, never
   instead of it. The RQ1 (C1 − C0) and RQ2 (C2 − C1) differences are shown per task and in
   aggregate. C2 vs C0 appears only as a labelled descriptive row.

   This is a presentation and accounting rule. It **does not change** the `task_success`
   definition (§4.1). Non-countable attempts are still never converted into task failures.
3. **Agent-time visualization.** One mark per countable attempt, grouped by task × configuration.
   C2 is split into phase 1 / phase 2 stacked to the total. Timeouts are marked at the cap. Failed
   and successful attempts are visually distinguished. There is no success-only plot without the
   full one.
4. **Changed-files / diff-size descriptive visualization.** Per attempt, within the frozen source
   scope, grouped the same way. Withheld diffs are marked, not zeroed.
5. **Failure-mode table.** Counts of the §4.1 failure categories per task × configuration, plus a
   separate table of non-countable attempts by validity / interruption class.
6. **Explicit limitations section.** At least: six task units; one task per language × type;
   three repetitions; one model, effort, CLI version and date range; one specific `CLAUDE.md`;
   one planning workflow under one budget; Pro-subscription execution; the §3 prohibitions.

**No significance testing** is proposed merely because there are 54 cells. The cells are not
independent tasks (§1), and protocol §1 already classifies any statistical test on this design as
exploratory.

## 9. Final-series harness blocker and status of drafting findings

### 9.1 Blocker at the protocol-draft baseline [R5, P4]

**At the Study-01 protocol-draft baseline commit `03646a8`, the published V1 series implementation
cannot execute the 54-cell Study-01 design.** Gate 2 (§10) is intended to remove this blocker.
This finding records the state at that baseline commit.

- At `03646a8`, the production series implementation supports only the pilot's **single
  repetition** (six planned cells):
  - readiness rejects `repetitions != 1` (`series.py` at `03646a8`, lines 199–200);
  - `generate_schedule` defines only the one-repetition, six-cell pilot order (lines 219–220).
- Study 01 requires **6 tasks × 3 configurations × 3 repetitions = 54 planned cells**, executed in
  the blocked-by-repetition, seeded, non-adaptive order of protocol §11 / F17.
- **Minimal generic repetition and scheduling support is a pre-freeze infrastructure
  prerequisite** (§10, gate 2).
- **This draft is not permission to implement it, and it has not been implemented.**
- The future implementation **must preserve the completed pilot's behavior and identities.** The
  frozen pilot `spec_hash`, `schedule_hash` and `cell_id`s (`PILOT_V1_CLOSEOUT.md` §2–§3) must
  still reproduce exactly. A backward-compatibility gate (§10, gate 3) verifies this.

### 9.2 Status of the other drafting findings

| ID | Finding | Status |
|---|---|---|
| F-2 | `result.duration_seconds` spans the lifecycle from the start of `RunLifecycle.execute` (`lifecycle.py` line 182) to finalize (line 387), so it is not agent time | Resolved by R2: §4.1 / §4.2 fix `process.json` (C0/C1) and `c2.json` (C2) as the source; the exact field binding is confirmed at freeze (C-b, §6.2) |
| F-3 | The initial `task_success` wording omitted the integrity requirement | Resolved by R1: `task_success` = existing `resolved` on a countable observation |
| F-4 | Protocol §1 lists C2 vs C0 alongside the other contrasts | Resolved by R3: two primary RQs; C2 vs C0 is descriptive only |
| F-5 | The replacement policy is frozen for the pilot only; O13 is open for final runs | Resolved in direction by R4 (§6.3); formal adoption remains freeze item C-a |
| F-6 | The previous F-TS-REF-01 had the same shape as P-TS-01 | Resolved by R6: replaced by the command-dispatch refactor (§5.7) |

## 10. Next-gate order [R8]

The gates run in this order. A gate starts only after the previous one is complete. Skipping or
reordering a gate requires a recorded protocol amendment.

| # | Gate | Exit criterion |
|---|---|---|
| 1 | **Operator protocol approval** | The operator approves this draft (still not frozen) as the basis for the following steps |
| 2 | **Minimal final-series harness support** | Generic repetition support and the protocol §11 blocked, seeded 54-cell schedule are implemented in a separate, reviewed task (§9.1), with model-free tests |
| 3 | **Regression / backward-compatibility gate** | Establishes and validates the **harness implementation candidate**. The full existing test suite passes. The frozen pilot-v1 `spec_hash`, `schedule_hash` and `cell_id`s reproduce exactly. A model-free dry series exercises 54 FINAL-namespace cells. The validated commit becomes the candidate `harness_git_sha` (§7.1) |
| 4 | **Final task authoring / validity** | The six final packages are authored independently under `PILOT_TASK_STANDARD.md` and pass the §11 validity gate with stored evidence (no model call) |
| 5 | **Remaining analysis / freeze decisions** | Closes the remaining experimental decisions: every §6.2 open decision and freeze confirmation has a recorded operator value |
| 6 | **Immutable Study-01 snapshot** | Writes the freeze material covering §7.2 (including `harness_git_sha`). Generates and finalizes the 54-entry schedule from the frozen seed. Computes the deterministic `study_snapshot_hash`. Commits the freeze artifacts. The commit SHA is **not** part of the committed content; once the commit exists, it is recorded as external provenance (`study_freeze_commit`, §7.1) |
| 7 | **Final execution** | 54 planned cells are executed **only under the already frozen snapshot**, with the §6.3 policy and the §7.3 no-change rules |
