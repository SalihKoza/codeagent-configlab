# CodeAgent ConfigLab — Pilot Plan (`pilot-v1`)

Status: **draft, 2026-09-27. Not yet frozen; no pilot task exists; no pilot run has been executed.**
This plan becomes binding for the pilot series when every "must freeze before pilot" row of the
decision table (§18) has a recorded value and the document is hashed. Task packages follow
`docs/PILOT_TASK_STANDARD.md`.

Tags as in the task standard: **[FROZEN]** = fixed by `docs/EXPERIMENT_PROTOCOL_V0.md`;
**[PILOT]** = proposed for `pilot-v1` only, never a final default by implication;
**[OPEN-FINAL]** = decided at the final freeze; **[OPERATOR]** = needs an operator choice before
pilot execution.

---

## 1. Purpose and non-goals

The pilot checks that the experiment machinery works on real tasks, with all three configurations,
inside the real harness:

- task packaging and the validity gate;
- treatment application (C0 has no `CLAUDE.md`; C1/C2 have the frozen one; C2 gets wrapper and
  approval message);
- C2 same-session continuation and phase-1 read-only in the real lifecycle;
- equal implementation envelopes (C0 = C1 = C2 phase 2);
- evaluator correctness (including rejecting known-wrong solutions) and post-agent independence;
- timeout behavior, error/validity classification, artifact completeness, provenance links;
- cleanup and start-of-run cleanliness.

Non-goals:

- **No configuration ranking or superiority claim.** Pilot outcomes are not reported as C0/C1/C2
  performance and never pooled with final runs [FROZEN F16, §9].
- No smoothing of performance numbers with more repetitions.
- No tuning of treatments, task wording or envelope based on which configuration did better (§14).

## 2. Pilot success is not agent task success

The pilot series can **PASS even if one or more agent attempts fail the coding task**. Pilot
success means the experiment correctly packages tasks, applies treatments, observes behavior,
evaluates output, classifies failures, preserves artifacts and cleans state. A correctly measured
and correctly classified C0, C1 or C2 coding failure is useful pilot evidence, not a defect.

## 3. Design

| Item | Value |
|---|---|
| Tasks | `P-PY-01` (Python, bug fix), `P-TS-01` (TypeScript, behavior-preserving refactor) — §4, §5 |
| Configurations | C0, C1, C2 [FROZEN definitions §3] |
| Repetitions | 1 |
| **Runs** | 2 × 3 × 1 = **6** |

Why this pairing: it covers both languages; the bug fix exercises ordinary
"acceptance fails on pristine" semantics; the refactor exercises the special no-op/structural
semantics (protocol §6, O15), which is the most fragile evaluator case; and it avoids authoring all
six task types before the method is proven.

Why one repetition: the pilot validates machinery and task/evaluator behavior, not within-cell
variability or configuration performance. Each mechanism the pilot must observe appears at least
once per task per configuration.

**Units — do not conflate:**

| Unit | Count in pilot | Note |
|---|---|---|
| Run (cell attempt) | 6 planned (+ replacements, §11) | protocol §2 |
| Claude CLI invocations | 8 planned | C0 = 1, C1 = 1, C2 = 2 (phase 1 new session, phase 2 `--resume`) per task |
| Model API requests | **unknown** | many per invocation; `num_turns` is emitted but its exact meaning is not yet verified (§12) |

**Pre-declared exception to "six runs".** If neither C2 run reaches phase 2 (e.g. both end during
phase 1), same-session continuation has not been observed in the real harness and exit criterion
§16-E3 cannot be judged. In that case, and only then, one additional C2 run is executed on
`P-PY-01` under the same pilot version. This rule depends on whether a mechanism was observed, not
on task success.

## 4. P-PY-01 — Python bug fix

> **PILOT ONLY — NOT ELIGIBLE FOR FINAL DATASET**

- **Concept.** A function that renders a sorted list of distinct integers as a compact range string
  drops or truncates the final group when the input ends with consecutive numbers.
- **Repository shape.** `rangefmt/__init__.py`, `rangefmt/core.py` (~40 lines, the function plus a
  tiny parser used elsewhere), `tests/test_core_public.py` (stdlib `unittest`), `README.md` with
  the test command. [PILOT] Use stdlib `unittest` only: WSL Python 3.14 has no pip (verified during
  setup), so the Python pilot needs no dependency preparation at all.
- **Public behavior (statement draft, one paragraph).** `collapse_ranges(values)` takes integers
  sorted ascending without duplicates (possibly empty, possibly negative) and returns groups joined
  by `,`; a group of one number is rendered as the number, a group of two or more consecutive
  numbers as `start..end`. The docstring already states this contract. Bug report: when the input
  ends with consecutive numbers the last group is rendered wrongly, e.g. `[4, 7, 8, 9]` gives
  `"4,7"` instead of `"4,7..9"`. The separator `..` is chosen so negative numbers are unambiguous
  (`-3..-1`).
- **Acceptance distinguishes.** Trailing group of length 2 and of length ≥ 3; input that is one
  group; trailing group after a singleton. Pristine fails for the intended reason (wrong string),
  not an exception.
- **Regression protects.** Empty input → `""`; singletons only; groups in the middle; negative
  numbers in the middle; the input list is not mutated (only if the docstring says so); the parser.
- **Hidden tests may probe** (all inferable from the docstring contract): single-element input;
  negative numbers in the trailing group; a length-2 trailing group; long inputs.
- **Likely reference class.** Flush the open group after the loop (one-location fix); an
  alternative is a rewrite by grouping consecutive values.
- **Known-wrong solutions.** (a) Handles a trailing group only when it has ≥ 3 elements; (b) appends
  the last value without checking whether it continues a group (`"4,7,9"`); (c) special-cases the
  example input.
- **Validity risks.** Very easy for the model (acceptable: the pilot needs a working bug-fix path,
  not difficulty); a well-known kata shape, so model prior knowledge is high; the `..` separator and
  the length-2 rule MUST be in the contract, or hidden tests become secret requirements; test data
  no longer needs to avoid strings like `401`: since G4 the outcome classifier reads only structured
  CLI fields, never task or model text.

## 5. P-TS-01 — TypeScript behavior-preserving refactor

> **PILOT ONLY — NOT ELIGIBLE FOR FINAL DATASET**

- **Concept.** Three exporters for a list of contact records each carry their own private copy of
  the same field-normalization logic; consolidate it into one shared function without changing any
  exporter output.
- **Repository shape.** `package.json`, `package-lock.json`, `tsconfig.json`,
  `src/{types,csv,json,markdown,index}.ts` (~150 lines total), `test/*.test.ts`, `README.md` with the
  build+test command. [PILOT] Toolchain: pinned `typescript` devDependency, compile then run
  `node --test` on the output; do not rely on Node's type-stripping flags unless verified for
  Node 22.23.2 at authoring time. `node_modules` is installed by the author from the lockfile
  before freezing and is part of the pristine fixture (O9 pilot mechanism, §15).
- **Public behavior / structural target (statement draft).** "Field normalization (trim, collapse
  internal whitespace to single spaces, `null`/`undefined` → empty string) is duplicated in
  `cleanCsvValue`, `cleanJsonValue` and `cleanMdValue`. Consolidate it: `src/normalize.ts` exports
  `normalizeField(value: unknown): string`; `csv.ts`, `json.ts` and `markdown.ts` import and use it,
  and the three old helpers no longer exist. Exporter-specific escaping (CSV quoting, Markdown
  pipe escaping) stays in its exporter. Exported signatures and all exporter outputs must not
  change."
- **Acceptance distinguishes (structural criterion, checked with the TypeScript compiler API).**
  `src/normalize.ts` exports `normalizeField`; each exporter imports it from `./normalize` and
  calls it; the three named helpers are absent. Pristine fails; a no-op fails. Hidden behavior
  tests of `normalizeField` itself, whose semantics equal the documented current helpers.
- **Regression protects.** Exact outputs of `toCsv`, `toJson`, `toMarkdown` on records containing
  surrounding and internal whitespace, tabs/newlines, `null`/`undefined`, quotes, commas and pipes.
- **Hidden tests may probe.** Any input within the declared types, because "outputs unchanged" is
  the public requirement.
- **Likely reference class.** New module + three imports; alternative valid solution:
  `normalizeField` written differently (e.g. split/join instead of regex), or exporters calling it
  through a small local wrapper — both must pass.
- **Known-wrong solutions.** (a) No-op; (b) adds `normalize.ts` but keeps the old helpers (dead
  abstraction); (c) consolidates but drops `null` → `""` in one exporter (regression fails);
  (d) moves CSV quoting into `normalizeField` (JSON/Markdown outputs change → regression fails).
- **Validity risks.** The three original copies MUST be semantically identical, otherwise
  consolidation silently changes behavior (hidden trap). The structural check cannot detect a
  duplicate re-inlined without a named helper while `normalizeField` is also called; this is a
  recorded residual risk, reviewed in each diff. Prescribing the file and export name is
  deliberate (the "module boundary" category of the standard §10) and is stated publicly. The build
  writes `dist/`, which must be declared in the package's `generated_outputs` (PILOT_TASK_STANDARD §13a). In C2 phase 1 the working copy is read-only, so
  a build there fails; that is recorded, not a violation (spike B).

## 6. Pilot run order

[PILOT] Outcome-independent, reproducible, written down before the first pilot run.

Procedure (generated once at pilot freeze with a few lines of stdlib Python, output pasted into
this section and hashed):

1. `seed = int(sha256(b"configlab-pilot-v1-order").hexdigest()[:8], 16)`;
   `rng = random.Random(seed)`.
2. `first = rng.choice(["P-PY-01", "P-TS-01"])`; tasks alternate starting with `first`.
3. For the first task, `rng.shuffle(["C0","C1","C2"])`; for the second task, shuffle again, and
   reshuffle until its permutation differs from the first.
4. Positions: `t1·c1, t2·c1, t1·c2, t2·c2, t1·c3, t2·c3`.

This avoids "all C0, then C1, then C2", spreads each configuration over early and late positions,
and needs no hand choices. Pauses (limit, infrastructure) resume at the next unexecuted position;
replacements are appended at the end (§11). The final 54-run order is **not** generated here
[OPEN-FINAL, §11 of the protocol].

## 7. Model

Evidence in the repository: the only model value ever used is `haiku`, resolved by the CLI to
`claude-haiku-4-5-20251001` (spike and WSL smoke), and both documents label it infrastructure-only
and **not** the O5 pin. `init.model` in stream-JSON reports the resolved model per invocation.

Decision rule [PILOT]:

- The pilot model SHOULD be the model intended for the final runs, because the pilot calibrates
  timeout feasibility and learns usage-field behavior, and both depend on the model. Piloting on a
  cheaper model would leave those calibrations untransferable.
- Pass the most specific identifier the CLI accepts for the Pro login; record both the requested
  value (`model_request`) and `init.model` for every invocation.
- The series is only consistent if `init.model` is identical across all pilot invocations; a
  mismatch makes the affected run `invalid:harness`.
- Other model-related settings: the envelope sets none (no effort/thinking flags); the pilot records
  this as "CLI default, not set". Adding any such flag is a new pilot version.
  **Superseded 2026-09-29:** the operator now requires an explicit effort level (below); the
  envelope sends `--effort` on every invocation. This is a new pilot version of that decision, not
  a correction of a bug.

**[OPERATOR]** Which model. Not derivable from the repository. Pilot model freeze ≠ final model
freeze: the final model is frozen separately (O5); if it differs from the pilot model, timeout and
usage observations must be re-checked before final runs. Whether a larger model uses up the Pro
allowance faster is plausible but **not verified** here.

**Frozen 2026-09-29 (operator).** Pilot `model_request = "claude-sonnet-5"` — the installed
Claude Code 2.1.263 CLI's documented full-name form for `--model` (`claude --help`: "...or a
model's full name (e.g. 'claude-fable-5')"); verified locally (no inference call) via the CLI's own
help text and this harness session's own resolved-model transcript record, never by an actual
pilot invocation. The literal string `"Default"` is explicitly rejected by
`RunManifest.validate()` — the provider default is not pinned, so it must never silently become
the frozen value. Effort level `effort_request = "high"`, sent via `--effort` (CLI-documented
choices: low/medium/high/xhigh/max), explicit on every invocation rather than inherited from
`settings.json`/session state, for the same reason. Both values apply identically to C0, C1 and
both C2 phases (they come from one frozen series spec into every attempt manifest, and C2's two
phases share one `RealAgentRunner` instance — see `docs/PILOT_SERIES_V0.md`). Record:
`treatments/pilot-v1/FREEZE.json`.

**Requested vs. observed — implemented 2026-09-29.** `session.observed_model_in_events()` reads
only the structured `model` field off the CLI's `type=="system"/subtype=="init"` stream-json
event — never assistant/tool text, never stderr, no alias normalization. `RealAgentRunner.run()`
records both `requested_model` (the value passed to `--model`) and `observed_model` into
`process.json` (and, for C2, separately into `phase1.process.json`/`phase2.process.json`, so both
phases' observed models are independently visible). `RunLifecycle.execute()` then enforces the
invariant this section already committed to above: once `model_request` is frozen and the run
reached `agent_outcome in {completed, timeout, error_exit}` (a genuine attempt occurred) with no
prior auth/limit/harness-level explanation, every phase's observed model must equal the requested
model; a mismatch sets `run_validity = invalid:harness` (exactly the mapping this section names
above) with a visible `invalid_reason`, never silently accepted. `AUTH_FAILURE`/
`LIMIT_INTERRUPTED`/`HARNESS_ERROR` outcomes are never overridden by this check (their own
classification already fully explains the run). **`ERROR_EXIT` is asymmetric (2026-09-29):** a
mismatch still fails closed exactly like `completed`/`timeout` — a wrong model must not become
invisible merely because the run later errored ordinarily — but a *missing* observed model (no
init event happened before the error) is never invented into a verdict: there is no
model-provenance evidence before init, so `error_exit` with no init keeps today's ordinary
`error_exit` semantics (`run_validity` untouched). `completed`/`timeout` keep the stricter
missing-is-invalid rule (a normally-progressing run with no captured model at all is anomalous).
The resulting `invalid:harness` attempt is automatically non-countable
(`status.derive_analysis_eligibility`) and already replacement-eligible
(`series.REPLACEMENT_ELIGIBLE_VALIDITY`) — no new status value or replacement policy was needed.
Evidence: `tests/test_outcome_classifier.py`'s `ModelProvenance` class (offline, synthetic +
preserved fixtures, no Claude call) and `tests/test_session.py`. See also
`docs/G4_OUTCOME_CLASSIFIER.md`'s "Model provenance" section for the full precedence rule.

**Verification-history note.** During the CLI-capability verification that froze `model_request`/
`effort_request`/`timeout_seconds` (2026-09-28/29): 1 accidental exploratory Claude invocation;
not a pilot cell and not executed through the benchmark lifecycle (`claude config list` was
parsed as a prompt by the installed CLI since `config` is not a recognized subcommand). No
pilot seed, model, or quota was touched by it. No further Claude call was made in this task.

## 8. Treatment artifacts for the pilot

### 8.1 `CLAUDE.md` — recommendation: one common, byte-identical file

[PILOT] One `CLAUDE.md` for both pilot tasks and both languages.

Rationale: it is the protocol default (§3.2); it minimizes treatment degrees of freedom (one hash,
one text); and language-specific repository facts (test commands, build step) belong in each
fixture's `README`, which all three configurations see. Putting them only in `CLAUDE.md` would give
C1/C2 information C0 lacks and would blur "instructions" with "task information". A per-language
variant is therefore not needed for the pilot; O14 remains [OPEN-FINAL].

Design constraints (the text itself is authored in the next task, then frozen and hashed):

- generic repository-level engineering guidance (e.g. inspect relevant code and tests before
  editing, keep changes scoped, preserve public interfaces unless asked, run the test suite before
  finishing, do not weaken or delete tests to make them pass);
- no task-specific content, no mention of hidden tests, evaluator, reference solutions, pilot or
  experiment; no expected implementation;
- no language- or tool-specific commands (those are in the README);
- stored under the harness root (`treatments/pilot-v1/`), copied into the C1/C2 working-copy root,
  and committed in the fixture's single baseline commit [FROZEN §3.2];
- SHA-256 recorded as `claude_md_hash`.

Relation to the final file: [PILOT] the pilot text SHOULD be written as the intended final
candidate. At final freeze it may be adopted unchanged or revised **only** for reasons unrelated
to configuration performance (e.g. a discovered leakage or ambiguity), recorded as a new version.

### 8.2 C2 planning wrapper and approval message

Not yet written (`session.py` holds placeholders). Constraints [FROZEN §8]: fixed across tasks and
runs; the wrapper embeds the unmodified task statement and asks for repository inspection and a
plan without modifying anything; the approval message is sent regardless of plan quality and
contains no reference to the plan. Both are authored with the `CLAUDE.md` text, hashed, and frozen
before the pilot.

### 8.3 Pilot treatment texts and seed — FROZEN (operator-approved 2026-09-28)

**Frozen.** The operator approved these exact bytes, and the file contents were re-verified before
freezing. The `CLAUDE.md` hash is the full 64-hex value: the operator report had shown a truncated
63-character prefix, which the operator then confirmed. Any byte change requires a new pilot version.
All files are UTF-8, no BOM, LF only, with exactly one trailing newline.
Record: `treatments/pilot-v1/FREEZE.json`. Checks, with the hashes pinned as literals:
`tests/test_treatment_candidates.py`.

| Item | File | Manifest field | SHA-256 |
|---|---|---|---|
| Common `CLAUDE.md` (C1 and C2, byte-identical; installed as `CLAUDE.md` at the WC root) | `treatments/pilot-v1/claude_md.md` | `claude_md_hash` | `213df66805a816a4dea6998580fd85c91c3d3a1beb08acb3dbdf7ddc000e0541` |
| C2 phase-1 planning wrapper (`{{TASK_STATEMENT}}` exactly once) | `treatments/pilot-v1/planning_wrapper.txt` | `planning_wrapper_hash` | `299b08446b440345a7f177258208c3bf8b1d33addc3934ed1356bb72a0c47fc4` |
| C2 fixed approval message | `treatments/pilot-v1/approval_message.txt` | `approval_message_hash` | `dbf445a514ca2ae9576935d09d7add9cf9157f88ca01ae1388d65a1f1009ee14` |
| Run-order seed text `configlab-pilot-v1-order` (§6, unchanged default; FROZEN) | — | `order_seed_text` | seed int `17271757` |

- The CLAUDE.md candidate deliberately does not encourage adding or updating tests. Public test
  files are protected paths, so such advice would push C1/C2 into
  `integrity=protected_path_modified`; the same unfairness applies to any protected path.
- The in-repo file is named `claude_md.md`, not `CLAUDE.md`, so tools working on the harness
  repository never load it as their own instructions.
- Model and timeout remain **[OPERATOR] / OPEN**. The six-cell schedule is not generated (it is
  generated by `series freeze` once the task packages exist).

## 9. Timeout

**What is measured.** Agent wall-clock: from spawning the first `claude` process of the run to the
exit of the last one, measured by the harness monotonic clock. Excluded: prepare, preflight,
capture, evaluation, cleanup, and any time spent waiting for a subscription limit to reset (a
limit-interrupted run ends; it is not paused and continued, protocol §10).

**C0 / C1.** One invocation, one cap `T`.

**C2.** One total cap `T` for both phases [FROZEN F5]. Phase 1 may use up to `T`; phase 2 is
started with the remaining budget `T − phase1_elapsed`. The inter-phase harness gap is measured and
recorded but not charged to the agent. If `T` expires in phase 1, phase 2 is not started and the run
ends as `timeout` [FROZEN §8]. [PILOT] No phase-1 sub-cap and no turn cap: each would add a treatment
degree of freedom, and the pilot should observe natural phase-1 durations first.

**On expiry.** The harness terminates the whole process tree (sandbox wrapper, CLI and its
children), confirms no agent process remains, then captures state [FROZEN §4]. Classification:
`agent_outcome=timeout`, run **valid**, evaluator runs on the final state — a timeout at the cap
is an experimental outcome, not an infrastructure failure. A hang caused by the harness or sandbox
machinery is `invalid:harness` (§10, ambiguous cases).

**Selecting `T`.** **[OPERATOR]** No repository evidence supports a value: the smoke's
`timeout=300` covered a one-line edit by an infrastructure model and is not evidence. Recommended
method: choose one round value before the pilot that is generous relative to the expected
solve time of a small task, so the cap rarely binds in the pilot and natural durations become
visible; the pilot then reports observed durations per run and per C2 phase, which inform O12 at the
final freeze. Quota is never spent to "discover" a timeout.

**Model-free verification (before the pilot).** Using the injectable `spawn` and local processes,
no Claude call:

- a child that sleeps past the cap → `timeout`, valid, process tree gone, artifacts written;
- a child that spawns grandchildren and ignores SIGTERM → whole tree killed;
- C2 with a phase 1 that consumes the budget → phase 2 not started, `timeout`;
- C2 remaining-budget arithmetic for phase 2;
- a runner exception unrelated to the cap → `invalid:harness`.

Status (2026-09-27): implemented and passing for single invocations — see G1 in §15. The two
C2-specific items need G2; the shared `Deadline` they rely on exists and is tested.

**Frozen 2026-09-29 (operator).** `T = 900` seconds. C0/C1 each get one 900s `Deadline`; C2 gets
one shared 900s `Deadline` across phase 1 + phase 2 (phase 2 never receives a fresh 900s — it gets
whatever phase 1 left). Evaluator and cleanup time stay outside this budget (unchanged, pre-existing
behavior). Record: `treatments/pilot-v1/FREEZE.json`.

## 10. Error and validity classification contract

Validity is classified from agent-phase evidence before evaluator results are looked at
[FROZEN F12]. Enum names are exactly those of `schemas/run-result.schema.json`.

| Situation | `agent_outcome` | `run_validity` | Counted as task outcome? |
|---|---|---|---|
| Agent exits by itself, evaluator verdicts recorded (pass or fail) | `completed` | `valid` | **yes** |
| Legitimate task failure (acceptance/regression `fail`) | `completed` | `valid` | **yes** (not resolved) |
| Non-zero exit caused by the agent's own behavior | `error_exit` | `valid` | **yes** |
| Cap reached | `timeout` | `valid` | **yes** |
| Agent edits protected paths | any | `valid`, `integrity=protected_path_modified` | **yes** (not resolved) [FROZEN F13] |
| Auth / 401 / service outage | `auth_failure` | `invalid:infrastructure` | no |
| Pro subscription limit | `limit_interrupted` | `valid`; `analysis_eligibility = not_countable:external_interruption` (G3) | **no** [FROZEN F18] |
| Harness crash / wrong configuration / envelope mismatch | `harness_error` | `invalid:harness` | no |
| Fixture hash mismatch | — | `invalid:fixture` | no |
| Hidden/reference material reachable | — | `invalid:leak` | no, and halts the series |
| State carryover detected | — | `invalid:carryover` | no, and halts the series |
| C2 phase-1 tree change / session break / wrong approval / phase-2 envelope ≠ C0/C1 | — | `invalid:c2_protocol` (`c2_protocol` = `phase1_write` / `phase_transition_failed`) | no |
| Instruction state changed during the run (§10 item 7) | any | `invalid:treatment_drift` | no (evaluated for diagnostics only) |
| Preflight failure (contamination, instruction files, versions) | `harness_error` | `preflight_failed` | no; run never started |
| Evaluator infrastructure failure | unchanged | unchanged | no: verdict pending, `analysis_eligibility = not_countable:evaluation_pending` (G8, below) |

**Pro limit and countability (G3, resolved 2026-09-28).** Subscription-limit interruption is an
external non-countable execution interruption. It is not a task failure, and not by itself a
protocol/harness-invalid run. `run_validity` answers only "was the run executed as specified?".
Whether an attempt counts as the planned observation for its cell is a separate axis,
`analysis_eligibility` (`result.json`). Its values come only from
`status.derive_analysis_eligibility(run_validity, agent_outcome)`:

| `run_validity` | `agent_outcome` | `analysis_eligibility` |
|---|---|---|
| `valid` | `completed`, `error_exit`, `timeout` | `countable` (legitimate outcome, incl. acceptance/regression fail) |
| `valid` | `limit_interrupted` | `not_countable:external_interruption` (`subscription_limit`) |
| any `invalid:*` / `preflight_failed` | any (auth → `invalid:infrastructure`, frozen) | `not_countable:invalid` |
| `valid` | `completed`, `error_exit`, `timeout` with `evaluator_error` or a verdict `not_run` | `not_countable:evaluation_pending` (G8) |

A valid `timeout` is countable; a limit interruption is not. That difference is the point of the
split. `status.check_status_consistency` rejects contradictory records (e.g. a limit recorded as
countable or as `invalid:infrastructure`, or with an evaluator verdict).
**Non-countable never means deleted:** every attempt keeps its run ID, manifest, phase evidence and
reason, and may later receive a predeclared replacement attempt (§11; linkage is G10).
The G4 limit detector is provisional. An invocation observed as `error_exit`
(`api_error_unclassified`) stays `error_exit` and is countable. It is never reinterpreted as a
limit after the fact; the reason code stays available for operator review.

**Evaluator failure.** `acceptance`/`regression = error` with `evaluator_error=true` is reserved for
failures of the evaluator itself (cannot start, hidden file missing, sandbox error). A failure that
originates in agent-written code (syntax/import error in a modified module, a test hanging in agent
code) is a task outcome: the verdict is `fail`. [PILOT] An evaluator infrastructure failure does not
change the run's validity; the evaluator is fixed and re-run on the preserved final state (needs
G7). This is re-evaluation of fixed agent output, not a rerun of the agent.
G8 (2026-09-28) makes this operational:
- The pending state is `analysis_eligibility = not_countable:evaluation_pending` (reason
  `evaluator_error` or `no_evaluator_verdict`). It is derived by the same canonical rule, and
  validity is unchanged. It is never countable, never `invalid`, and never an agent rerun.
- Evaluator infrastructure errors include:
  - sandbox initialization, preflight or post-flight failure;
  - termination failure;
  - missing hidden material or a missing pristine root;
  - candidate-copy or restore failure;
  - the evaluator raising;
  - a check whose exit status the in-sandbox launcher did not attest (srt failed mid-run);
  - an `evaluator.json` that cannot be finalized.
- A check that ran in the sandbox and returned nonzero, or hit its evaluator timeout, is `fail`.
- Output that trips the artifact secret scan is withheld (size-only placeholder) and the verdict
  stands.
- Executing re-evaluation is an operator/driver step (G10).

**Nonzero exit is not automatically infrastructure.** `error_exit` is the default for a nonzero exit
without an infrastructure marker; reclassification to `invalid:infrastructure`/`invalid:harness`
requires positive evidence (below).

**Ambiguous cases (resolved by recorded operator judgment from agent-phase evidence, before scoring):**

1. Nonzero exit with a CLI-internal crash trace not triggered by any tool call → `invalid:infrastructure`; otherwise `error_exit`.
2. Timeout where the last events show a tool call blocked in sandbox machinery (bwrap/srt hang) → `invalid:harness`; a timeout while an agent-started process runs (server, infinite loop) → valid `timeout`.
3. Infrastructure marker present but the run otherwise completed normally → classify by the `result` event (`is_error`, `api_error_status`, `terminal_reason`) and the CLI's API-error wrapper, never by substring matches in agent text. Implemented by G4 (`outcome_classifier.py`, `docs/G4_OUTCOME_CLASSIFIER.md`).
4. Phase-1 write attempt blocked by enforcement → not a violation, recorded [FROZEN §8].
5. Agent code makes an evaluator test hang → `fail` at the evaluator's own timeout, valid.
6. [PILOT] C2 phase 1 ends with `error_exit` → the run ends there as a valid `error_exit`; phase 2
   is not started (protocol §4: "phase 1 if the run cannot continue"). If phase 1 ends normally
   exactly as the budget runs out → `timeout`, and phase 2 is not started.
7. **Treatment-state invariant (decided 2026-09-27).** The instruction state is every
   `CLAUDE.md` / `CLAUDE.local.md` at any depth, plus everything under any `.claude/` directory.
   It must equal the expected state at agent start: the frozen treatment (C1/C2) plus the exact
   Candidate-2 seeds. It must still be identical at agent end. Any creation, modification or
   deletion → `run_validity=invalid:treatment_drift`. The run is not comparable. Nothing is
   restored or hidden, and the evaluator still runs for diagnostics. There is no new filesystem
   restriction. Precedence: infrastructure > C2 protocol > treatment drift.

## 11. Rerun policy (`pilot-v1`)

[PILOT] Frozen before any pilot outcome is seen; satisfies protocol §10 constraints.

**No rerun (valid outcomes):** acceptance or regression failure; agent `error_exit`; valid
`timeout`; integrity violation; blocked phase-1 write attempt.

**Replacement-eligible (never automatic; operator decides from agent-phase evidence, recorded):**
`invalid:infrastructure` (auth/outage), `limit_interrupted` (after the limit resets),
`invalid:harness`, `invalid:fixture` (only when the materialized copy was corrupted and the frozen
package itself is correct — the replacement uses the **same** task version; if the package itself
must change, that is a new pilot version, see "Halt and review"), and `preflight_failed` (after the
environment is fixed; the run never started).

A replacement after an `invalid:harness` whose fix changes harness code that affects the manifest
identity, evaluator verdicts or the envelope is not a replacement: it triggers a new pilot version
(§14).

Rules:

- at most **one** replacement per cell;
- the original record is kept untouched (it stays `not_countable:*`, never deleted); the replacement gets a new `run_id`, the next attempt
  number, a fresh working copy and a new session;
- the link original → replacement and the reason are recorded in the pilot log (the run-result
  schema has no link field; see §18 row "classifier behavior" / G10);
- replacements are executed after the last planned position, in original order;
- the decision never looks at evaluator verdicts;
- if the replacement is also invalid, the cell is reported as "no valid attempt" (never imputed),
  and exit criteria are judged with that gap disclosed.

**Halt and review:** `invalid:leak`, `invalid:carryover`, or a `phase1_write` caused by failed
enforcement stop the series. Affected runs are identified. If the fix changes the harness, envelope,
treatment or a task package materially, the series restarts as `pilot-v2` with all six cells; runs
of different pilot versions are not mixed.

## 12. Usage and token fields

Evidence: stream-JSON `result` events carry `usage.*`, `modelUsage`, `duration_ms`,
`duration_api_ms`, `total_cost_usd`, `num_turns` (spike C); their meaning under a subscription is
unverified (O8). The run-result schema intentionally has no usage field (`RUN_MANIFEST_V0.md`).

[PILOT] Policy:

- **Raw fields preserved:** the complete stream is already stored per run as `events.jsonl`
  (per invocation for C2 once G2 exists: `phase1.events.jsonl` is on the artifact allowlist).
  Nothing else is extracted into `result.json`.
- **Derived fields:** none.
- **Primary duration:** harness-measured agent wall-clock (§9), per run and per C2 phase.
  CLI `duration_ms` is kept raw as a secondary observation.
- **C2:** phase-1 and phase-2 values are **never summed** until it is verified whether a resumed
  invocation reports per-invocation or cumulative session values. Pilot check: compare phase-2
  `num_turns`/`usage` with the number of assistant turns actually present in phase-2 events.
- **Missing or unknown values** are recorded as absent/`null`, never `0`.
- `total_cost_usd` is not a billed amount under a Pro subscription and is not reported as cost.

The pilot's output for O8 is a short field-semantics note (field, present in which invocations,
per-invocation vs cumulative, stable or not).

## 13. Artifacts and provenance checked per run

Per protocol §7 and the WSL smoke artifact set: `manifest.json`, `result.json`, `preflight.json`,
`changed_files.json`, `evaluator.json`, `events.jsonl` (C2: plus phase-1 events), `stdout.txt`,
`cleanup.json`; plus, once G7 is fixed, the final diff. Checks: `run_id` identical in manifest,
result and results directory; working-copy directory name equals `workspace_token`;
`task_statement_hash`, `claude_md_hash`, wrapper/approval hashes equal the frozen values; secret
scan of the results directory clean (including the run canary).

## 14. What the pilot may change afterwards

Allowed, only when motivated by pilot evidence, each documented and versioned: evaluator bugs,
packaging defects, classifier errors, an unusable timeout, manifest/result field ambiguity,
cleanup or preflight defects.

Not allowed on the basis of which configuration did better: `CLAUDE.md`, wrapper, approval
message, task wording, or the envelope.

A change that affects comparability (anything in the manifest identity, evaluator verdict logic, or
envelope) invalidates mixing: the whole affected pilot series is re-run under a new pilot version.

## 15. Harness gaps to close before pilot execution

Verified in source on 2026-09-27 (`src/codeagent_configlab/`). Each is a small, separate
implementation task; none is fixed in this document.

| ID | Gap | Evidence | Needed for |
|---|---|---|---|
| G1 | **RESOLVED 2026-09-27.** Was: cap expiry raised `TimeoutExpired` → `invalid:harness`; `subprocess.run` killed only `srt`, leaving the `bwrap --new-session` subtree (and so `claude`) running. Now: `process_control.run_with_deadline` runs the agent in its own session, and on expiry terminates the process group plus every `/proc`-tracked descendant, identified by `(pid, starttime)` (SIGTERM, then SIGKILL after a grace period) → `agent_outcome=timeout`, run `valid`, `agent_exit_code=null`, partial output kept, `process.json` written. If termination cannot be confirmed → `harness_error` / `invalid:harness`. `Deadline` can be shared by C2's two phases (G2). Evidence: `tests/test_process_control.py` (WSL, 12 tests), `tests/test_runners.py` and `tests/test_lifecycle.py` G1 tests, and a model-free real `srt` probe as `cclab` in which all 11 tracked processes were terminated, 7 of them outside the run's process group. | `process_control.py`, `runners.py`, `lifecycle.py` | §9, §10 |
| G2 | **RESOLVED 2026-09-27.** Was: one invocation per run, no phase-1 checks, no wrapper/approval delivery, and a broken continuity never made a run invalid. Now `orchestration.run_agent_condition` runs one invocation for C0/C1. For C2 it runs phase 1 (`planning_envelope`, `--session-id <uuid>`, frozen wrapper containing the statement) and then phase 2 (the same implementation envelope as C0/C1, `--resume <uuid>`, frozen approval text). Phase 1 is verified read-only: the whole working copy is hashed except `__pycache__`; the project dir may hold only `<uuid>.jsonl` and an empty `memory/`; the user-level instruction check is re-run. A write → `phase1_write`; a session mismatch → `phase_transition_failed`; both → `invalid:c2_protocol`, phase 2 not started or not scored. One G1 `Deadline` covers the run, and phase 2 gets what phase 1 left (the inter-phase gap is not charged). Evidence: `tests/test_orchestration.py`. | `orchestration.py`, `lifecycle.py`, `runners.py`, `treatment.py` | C2 runs |
| G3 | **RESOLVED 2026-09-28.** Was: a limit-interrupted run was `run_validity=valid`, and `valid` was documented as "counts as a task outcome"; the countable predicate existed only as prose. Now validity means only "executed as specified", and a separate derived axis `analysis_eligibility` (`countable` / `not_countable:external_interruption` / `not_countable:invalid` + reason) comes from one canonical rule, `status.derive_analysis_eligibility`. It is stored in `result.json` as an additive `v0` field and enforced by `status.check_status_consistency`. The limit stays `valid` and is non-countable; auth stays `invalid:infrastructure`; timeout stays countable. Evidence: `tests/test_analysis_eligibility.py`. | `status.py`, `result.py`, `run-result.schema.json` | §10 counting |
| G4 | **RESOLVED 2026-09-28.** Was: `classify_outcome` substring-matched `401`/`quota`/… over stderr and every serialized event. A real successful stream was therefore `auth_failure` because an event `uuid` contained `401`; the successful G11 smoke was misclassified the same way. Now `outcome_classifier.classify_invocation` reads only CLI-set top-level fields, never text or stderr: the terminal `result` (`is_error`, `api_error_status`, `terminal_reason`), the API-error wrapper (`is_api_error_message` + `error` enum), `api_retry` and `rate_limit_event.status`. Auth = terminal API error with 401 or an auth code. Limit = terminal API error with a limit code **and** a `rejected` rate-limit event; this rule is provisional because no real one has been observed. Other API errors → `error_exit` (unclassified reason). An informational `rate_limit_event` is non-fatal. Timeout precedence is explicit and tested; G1 is unchanged. The reason and evidence go in `process.json.classification` and `invalid_reason`/`interruption_reason`; no schema change. Evidence: `docs/G4_OUTCOME_CLASSIFIER.md`, `tests/test_outcome_classifier.py`, `fixtures/g4-classifier/`. | `outcome_classifier.py`, `runners.py` | §10 |
| G5 | **RESOLVED 2026-09-27 (sandboxing: G5s, resolved 2026-09-28).** `task_evaluator.TaskEvaluator` works on a copy of the candidate state. It restores task-level protected paths from the pristine fixture (a path absent there is removed; an agent change → `integrity=protected_path_modified`) and injects hidden tests into the copy only. It then runs acceptance, optional structural (folded into the acceptance axis) and regression commands with a fixed minimal env and G1 process-tree timeouts. Exit 0 = pass, other = fail, a timeout = fail; a spawn failure, `error_codes`, missing hidden material or failed restore = `error`. `evaluate_candidate`/`overlay_candidate` serve offline validity gates. Evidence: `tests/test_task_evaluator.py`, WSL script. | `task_evaluator.py` | every task |
| G5s | **RESOLVED 2026-09-28.** Was: evaluator commands ran agent-written code unsandboxed as `cclab`. Now every check runs through `evaluator_sandbox.SrtEvaluatorSandbox` (the `command_wrapper` seam, `TaskEvaluator.sandbox`): a dedicated srt 0.0.77 policy (`g5s-v1`; `g5s-v2` since G8 adds the check launcher), independent of the agent sandbox, with `denyRead: ["/"]`. Read/write is limited to the evaluator copy and a private HOME/TMPDIR; read-only access covers system dirs, the pinned `node` binary and srt's seccomp helper; there is no network and AF_UNIX is blocked; `/tmp/claude` is read-denied (entries) and write-denied. The G1 process-tree timeout is unchanged. It fails closed: no sandbox, an init error, or a preflight/post-flight failure → `evaluator_error`, never an unsandboxed rerun. The policy hash and identity are in `evaluator.json.sandbox`, and the policy is identical for C0/C1/C2. Evidence: `docs/G5S_EVALUATOR_SANDBOX.md` (WSL matrix), `tests/test_evaluator_sandbox.py`, `tests/test_task_evaluator.py`, `spike/g5s-evaluator-sandbox/g5s_probe.py`. | `evaluator_sandbox.py`, `task_evaluator.py` | every real run |
| G6 | **RESOLVED 2026-09-27.** `baseline.create_baseline`: `git init --template=`, one commit with fixed neutral metadata and host git config isolated. It is deterministic (same fixture → same id), and C0/C1/C2 share the same commit (the observed commit must equal `cached_expected_baseline_commit`, else preflight fails). The commit is made before the seeds and the treatment, which stay uncommitted. A pristine fixture containing `.git` is refused. Final `HEAD` is read from files, never by running git on agent-controlled `.git`. Evidence: `tests/test_baseline.py` (incl. a scan of all git objects for reference/hidden markers), WSL script. | `baseline.py`, `workspace.py` | protocol §4 |
| G7 | **RESOLVED 2026-09-27.** Was: no final identity and no diff (the lifecycle never deleted the working copy; the WSL smoke removed its whole root). Now, before any evaluator copy exists, the harness writes `start_state.json` (agent-visible start = pristine + seeds + treatment), `final_state.json` (tree hash, HEAD, `head_moved`), start-relative `changed_files.json` (added/modified/deleted/renamed) and `final.diff`. `.claude/` is no longer excluded; only `.git`, `__pycache__` and `.pytest_cache` are. Evidence: `tests/test_agent_state.py`. | `agent_state.py`, `lifecycle.py` | §10, §5 review |
| G8 | **RESOLVED 2026-09-28.** Was: `evaluator_error` had no rule tying it to validity or countability. A mid-check srt failure read as `fail`. An evaluator exception, a candidate-copy failure or a secret-scan refusal of `evaluator.json` crashed `RunLifecycle.execute` (no `result.json`). A missing pristine root silently removed protected paths. Now each check runs through an in-sandbox launcher that attests the exit status (policy `g5s-v2`); unattested or mismatched → `error`. `lifecycle._evaluate_and_record` is the single guarded evaluate/record step. Validity is unchanged (§10), and `derive_analysis_eligibility` gives `not_countable:evaluation_pending`. `check_status_consistency` requires `evaluator_error` ⇔ an `error` verdict, and a `pass`/`fail` verdict ⇒ an `evaluator.json` ref. Evidence: `tests/test_g8_evaluator_errors.py`, `tests/test_evaluator_sandbox.py` (real srt mid-run failure on WSL). | `task_evaluator.py`, `lifecycle.py`, `status.py`, `evaluator_sandbox.py` | §10 |
| G12 | **RESOLVED 2026-09-28.** Was: an agent-side artifact containing a scanner marker raised `ArtifactSecretError` out of `RunLifecycle.execute` before `_finalize`. That meant no `result.json` and **no cleanup**. The `ArtifactSecretError` message itself echoed the matched markers, and G7's `final_diff_withheld` stored that message, so an agent diff containing `sk-ant-` crashed at `final_state.json`. Now `ArtifactStore.write_safe` is the one primitive, shared with G8's `withhold_markers`. It never raises for content or storage: JSON/JSONL artifacts keep their structure with offending strings/keys replaced by size-only placeholders; text artifacts become placeholder files (withheld ≠ absent); nothing is hashed. Storage/serialization failures are `write_failed` (`artifact_write_failed` / `artifact_serialization_failed`), never `content_withheld`. `artifact_report.json` records safe metadata, and scanner error messages are marker-free. `_finalize` always cleans up first. Withheld content leaves outcome, validity and eligibility unchanged; evidence that could not be stored → `invalid:harness`. An unstorable `result.json`/`manifest.json` → `ArtifactFinalizationError` after cleanup. `result.audit_run_directory` is the canonical invariant. Evidence: `tests/test_g12_artifact_withholding.py`. | `artifacts.py`, `lifecycle.py`, `agent_state.py`, `result.py` | auditable attempts |
| G9 | **RESOLVED 2026-09-27.** Was: the ancestor check also covered the working copy itself, and no step existed to put the treatment into the working copy. Now the treatment is copied into the working-copy root from the operator source, and the expected state comes from the manifest hashes. The ancestor check covers strict parents only. `treatment_instruction_files` requires exactly `{}` for C0 or exactly `CLAUDE.md` with the manifest SHA-256 for C1/C2 (no `CLAUDE.local.md`, and nothing shipped in the pristine fixture). `treatment_provenance` fails on a statement, `CLAUDE.md`, wrapper or approval text that doesn't match the manifest. The user-level check is unchanged. Evidence: `tests/test_preflight_real.py` (G9 section), `tests/test_orchestration.py`, `tests/test_treatment.py`. | `preflight.py`, `treatment.py`, `workspace.changed_files(expected_extra=)` | C1/C2 runs |
| G10 | **RESOLVED 2026-09-28.** Was: no task-package loader, no series driver and no replacement link; smoke wiring was hard-coded. An explicit `budget_seconds` silently overrode the manifest timeout, and `RealAgentRunner.model` was independent of `manifest.model_request`. Now: `task_package.TaskPackage` (version hash per the task standard §13; gate `PASS` must match the bytes). `series.Series` provides a frozen spec + the exact §6 schedule, deterministic `cell_id`s, opaque attempt ids with manifest linkage (`cell_id`, `attempt_ordinal`, `attempt_kind`, original/predecessor, reason), an append-only event log with derived cell states, resume, and ambiguous-attempt detection + `recover`. `replacement_decision` implements §11 (operator approval, at most 1 per cell, halt classes); `reevaluate` implements §10 for `evaluation_pending`. Readiness refuses `OPEN` model/timeout/treatment and ungated packages. The lifecycle refuses a budget or runner model that differs from the manifest. Verified by a dry six-cell series through injected runners (`tests/test_series.py`); see `docs/PILOT_SERIES_V0.md`. The E3 contingency run stays an operator decision. **Updated 2026-09-29:** `effort_request` (frozen `high`) now participates in the same frozen-manifest / fail-closed enforcement as `model_request` and `timeout_seconds` — readiness refuses it while `OPEN`, it is part of `spec_hash` and `frozen_cell_spec_hash`, and the lifecycle refuses a runner whose effort differs from the manifest. | `series.py`, `task_package.py`, `lifecycle.py`, `manifest.py` | executing the series |
| G11 | **RESOLVED 2026-09-28.** The real `G11_TREATMENT_LOAD_SMOKE_ONLY` passed. The repository CLAUDE.md marker was observed before any CLAUDE.md-reading tool call; the expected session was used; exit 0. Candidate-2 `.claude` immutability held and AF_UNIX stayed blocked for model Bash; the project settings hook did not run; cleanup left no residue; auth stayed claude.ai/firstParty/Pro. The same successful run was recorded as `auth_failure`, which exposed the G4 false positive (resolved above). History (status on 2026-09-27 was BLOCKED on infrastructure): The 2.1.263 binary confirms that `--setting-sources ""` disables the cwd memory walk. Chosen loader, common to C0/C1/C2 and both C2 phases: keep `--setting-sources ""` and add `--add-dir <wc>` + `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`, which loads `<wc>/CLAUDE.md`, `.claude/CLAUDE.md` and `.claude/rules` as Project memory without activating project settings. `<wc>/.claude` is made immutable in every phase (outer srt denyWrite, inner denyWrite, `Edit()` deny), because `--add-dir` also reads plugin enablement, agents and skills from it. Seeding is extended with empty `.claude/commands` and `.claude/agents`. Rejected: `--setting-sources project` (activates hooks/env/permissions/sandbox merge) and `--system-prompt-file` (different treatment). The first approved smoke got `401 OAuth access token has expired` (operator re-login); the rerun after re-login proved positive load. See `docs/G11_TREATMENT_LOAD_SMOKE.md`. | `envelope.py`, `runners.py`, `workspace.py` | C1/C2 validity |

Also required before the pilot (not code gaps): `node_modules` for `P-TS-01`, prepared by the
author and hashed [O9/§4]. The per-language ignore list is **implemented (2026-09-28)** as the
package-owned `generated_outputs` field (PILOT_TASK_STANDARD §13a). Python needs nothing beyond
the built-in `__pycache__`/`.pytest_cache` handling. `P-TS-01` declares its build outputs (e.g.
`dist/**`, `*.tsbuildinfo`) when it is authored and gated; that declaration is part of its version.

## 16. Pilot exit criteria

All must hold to proceed to final preparation. **Not required:** that any coding attempt succeeds.

**Task packages**
- T1 Both packages passed the validity gate (`PILOT_TASK_STANDARD.md` §11) with stored evidence.
- T2 Reference solutions pass; known-wrong solutions (and for `P-TS-01` the no-op) are rejected.

**Execution**
- E1 Each of the six cells has a valid result or a correctly classified interruption.
- E2 Task statement bytes identical across C0/C1/C2 per task (hash equality).
- E3 C1/C2 `CLAUDE.md`, wrapper and approval hashes equal the frozen values; C0 has none.
- E4 C2 same-session continuation verified in the real harness (`session_id` equal in both phases).
- E5 C2 phase 1 left the working copy unchanged (tree hash) and the project dir clean.
- E6 Implementation envelopes equal across C0, C1, C2 phase 2 (`init.tools`, `permissionMode`,
  `mcp_servers`, `model`, settings/policy hashes).

**Evaluation**
- V1 Evaluator ran only after agent termination, on a copy.
- V2 Acceptance/regression/integrity verdicts are explicable from the diffs.
- V3 Agent-modified public tests cannot produce a hidden-evaluator pass (protected-path restore
  shown on at least one known-wrong case that edits tests).

**Isolation and state**
- S1 Hidden/reference material unreachable (canary probe on the real task layout).
- S2 Preflight ran and passed (or correctly refused) for every run.
- S3 No unexplained state carryover between runs; cleanup reports succeed; auth intact.

**Artifacts and provenance**
- A1 Manifest, result, workspace and run IDs link correctly for every attempt.
- A2 Expected artifacts complete; secret/canary scan clean.

**Operational policy**
- P1 Timeout behavior verified model-free (§9) and understood in real runs.
- P2 The classifier handled every observed case; auth/limit logic tested model-free on fixtures.
- P3 The rerun policy classified every interruption that occurred.
- P4 Usage-field semantics note written (§12), including the C2 per-invocation/cumulative answer
  or an explicit "unknown".

**Decision gate**
- G No unexplained infrastructure error or methodological leakage remains that would compromise
  final-run validity.

## 17. Final-task firewall

[FROZEN F16] Pilot repositories, statements, hidden tests, known-wrong solutions, failure modes and
solutions MUST NOT become final tasks. Final tasks reuse only the abstract categories and are
independently authored. [PILOT] Final tasks also avoid the pilot problem domains (integer range
formatting; exporter field normalization). No pilot task is promoted after its outputs are seen.

## 18. Decision triage

| Decision | Existing frozen state | Pilot recommendation | Freeze before pilot? | May change before final? | Rationale |
|---|---|---|---|---|---|
| Pilot model | **FROZEN 2026-09-29**: `claude-sonnet-5` (was O5 open; `haiku` used only for infra) | intended final model; full id; record `init.model` — **[OPERATOR]** picks | done | yes (O5 separately) | calibrations depend on model |
| Effort level | **FROZEN 2026-09-29**: `high`, sent via `--effort` (supersedes "none set by envelope") | explicit per invocation, never inherited from session/settings defaults — **[OPERATOR]** picks | done | yes | reproducibility; avoid silent inheritance |
| Timeout `T` | **FROZEN 2026-09-29**: `900` seconds (was O12 open; one cap, C2 total [F5]) | generous round value — **[OPERATOR]** picks; no sub-cap, no turn cap | done | yes (O12) | observe natural durations |
| `CLAUDE.md` form | default one file [§3.2]; O14 open | one common byte-identical file; repo facts in README | **yes** | yes (O14; non-performance reasons only) | minimal treatment DoF, no C0 disadvantage |
| `CLAUDE.md` text, wrapper, approval | **FROZEN 2026-09-28** (§8.3; hashes in `treatments/pilot-v1/FREEZE.json`) | — | done | only for non-performance reasons, as a new version | treatment must exist to pilot C1/C2 |
| Pilot run order | F17 applies to final | seeded task-alternating order (§6); seed text `configlab-pilot-v1-order` **FROZEN 2026-09-28**; schedule generated by `series freeze` once packages, model and timeout exist | **yes** | n/a (final order separate) | outcome-independent, no clustering |
| Rerun policy | O13 open, §10 constraints | §11 | **yes** | yes (O13) | must precede outcomes |
| Classifier behavior (G3, G4, G8) | taxonomy frozen [§6, schema] | countable predicate (§10); result-event-only markers; evaluator-error rule. G3 decided (2026-09-28): (A) keep `run_validity` unchanged plus an additive derived `analysis_eligibility` field (no `invalid:subscription_limit`, no `v1`) | **yes** | yes | avoid misclassifying valid runs |
| Usage-field capture | O8 open; no schema field | raw only, no derived, no C2 sum (§12) | yes | yes (O8) | semantics unknown |
| Python bug-fix concept | — | `P-PY-01` (§4) | yes (after gate) | n/a (pilot-only) | ordinary acceptance semantics |
| TypeScript refactor concept | O15 open | `P-TS-01` (§5) with compiler-API structural check | yes (after gate) | n/a (pilot-only) | exercises no-op loophole |
| Dependency preparation | O9 open | Python: stdlib only; TS: author-installed `node_modules` in fixture, hashed | yes | yes (O9) | agent has no network |
| Evaluator determinism N | §6 requires determinism | N = 3 | yes | yes | tiny offline fixtures |

## 19. Protocol open-item status (for orientation; the protocol table itself is unchanged)

| # | Status after spike + WSL gate | Pilot role |
|---|---|---|
| O1 | Resolved for the harness (spike B) | confirm in real lifecycle (E5), needs G2 |
| O2 | Resolved for the harness (spike A) | confirm in real lifecycle (E4), needs G2 |
| O3 | Credential part: A1. Cleanup mechanism: spike D. Cross-run carryover probe: pending | S3 |
| O4 | Credential part: A1. Canary boundary: spike E + WSL gate. Real-task placement: pending | S1, gate item 9 |
| O5 | Open | §7 |
| O6, O7 | Resolved for the harness (spike C) | E6 |
| O8 | Open | §12 |
| O9 | Open | §15, §18 |
| O10 | Partly (exact slug removal); `/tmp/claude` shared | S3 |
| O11 | Heuristic only | G4, P2 |
| O12 | Open | §9 |
| O13 | Open | §11 (pilot only) |
| O14 | Open | §8.1 (pilot only) |
| O15 | Open | §5 (pilot only) |
| O16 | Open | final order only |

## 20. Sequence from here

1. Operator decisions (§18 [OPERATOR] rows).
2. Close G1–G10 (small, separately reviewed tasks; model-free tests).
3. Author `CLAUDE.md`, wrapper, approval message; freeze and hash.
4. Author both pilot packages; run the validity gate (no model call).
5. Generate and record the run order (§6); freeze this plan.
6. Execute the six runs; classify; write the pilot report.
7. Narrow fixes (§14); pilot exit decision (§16).
