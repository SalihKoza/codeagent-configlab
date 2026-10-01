# CodeAgent ConfigLab — Experiment Protocol V0

Status: **design freeze, pre-harness.** This document fixes the methodological
contract before any harness code exists. Harness implementation must conform to
it; where it cannot, the protocol is amended explicitly (versioned, dated,
with the reason) — never silently.

Terminology: **MUST / MUST NOT** are binding for final runs. **OPEN** marks a
question that is not yet decided and must be resolved (usually by a technical
pilot) before the item it blocks. Anything not stated here is not assumed.

Baseline environment (frozen, verified during setup; see `setup/`):
WSL2 Ubuntu 26.04, user `cclab`, Claude Code 2.1.263, Node 22.23.2, npm 10.9.8,
`@anthropic-ai/sandbox-runtime` 0.0.77, persisted Claude.ai login on the existing
Claude Pro subscription, headless `claude -p` confirmed, `claude_sanitized`
(`setup/common.sh`) confirmed, filesystem / network / AF_UNIX sandbox
enforcement confirmed, `/mnt/c` hideable from the sandbox view.

---

## 1. Research question

**V0 asks:** on a fixed set of six small synthetic coding tasks (three Python,
three TypeScript: one bug fix, one small feature, one behavior-preserving
refactor per language), executed headlessly by one pinned Claude Code version
with one model on a Claude Pro subscription, how do task-resolution outcomes and
execution cost (wall-clock, and usage fields where the CLI exposes them) differ
between:

- **C1 vs C0** — adding one fixed, version-controlled repository instruction file;
- **C2 vs C1** — additionally imposing an explicit read-only planning phase,
  followed by a fixed approval message, in the same session;
- **C2 vs C0** — the combined effect of both.

**V0 can show:** descriptive, per-task and aggregate differences observed on
these 6 tasks × 3 repetitions, under this exact environment, version and date
range, together with the run-to-run variability of each cell.

**V0 cannot show, and MUST NOT be reported as showing:**

- that any configuration is "best" or superior in general;
- effects on other tasks, languages, repository sizes, real-world codebases,
  other models, other Claude Code versions or other CLAUDE.md contents;
- the effect of Claude Code's built-in plan permission mode as a product
  feature (C2 is a workflow, see §3 and §8);
- statistically confirmatory effects: with 6 tasks and 3 repetitions, any
  statistical test is exploratory and is reported as such;
- causal claims about *why* a configuration helped (mechanism), beyond the
  observable artifacts.

The unit of generalization is at most "these tasks, this setup". Tasks are the
dominant source of variance; results are always reported per task alongside any
aggregate.

## 2. Experimental unit

One **run** = one `(task, configuration, repetition)` cell executed once:

- `task` ∈ the 6 final tasks (pilot tasks are never cells, §9),
- `configuration` ∈ {C0, C1, C2},
- `repetition` ∈ {1, 2, 3}.

6 × 3 × 3 = **54 final runs**. Each run has a unique run ID; a cell may have more
than one *attempt* only under the invalid-run policy (§10), and every attempt is
kept.

Repetitions are **independent attempts**, not continuations or retries:

- each starts from its own fresh copy of the pristine fixture (§4);
- each starts a new Claude session; no `--continue` / `--resume` / session ID
  from any other run is ever used (C2's in-run phase continuation is internal to
  one run, §8);
- no memory, transcript, file or output from any other run is visible (§4, §5);
- a repetition is executed regardless of the outcome of earlier repetitions and
  is never triggered by, or skipped because of, an earlier result.

Rationale: model sampling is nondeterministic and not seedable through the CLI.
Repetitions estimate this within-cell variability. If repetition *k* could see
repetition *k−1*, it would measure learning-from-previous-attempt, which is not
the research question.

## 3. Treatment definitions

### 3.1 Identical execution envelope (C0, C1 and C2 phase 2)

The implementation envelope below MUST be identical for C0, C1 and C2's
implementation phase (phase 2). C2's planning phase (phase 1) intentionally
differs in permissions / tool availability / write access, because read-only
planning is the treatment (§8). All other non-treatment conditions MUST be
identical across C0, C1 and both C2 phases.

| Element | Requirement |
|---|---|
| Machine / OS / user | same WSL2 host, user `cclab`, same HOME |
| Tool versions | Claude Code, Node, npm, sandbox-runtime, Python, rg, bwrap exactly as frozen; recorded per run |
| Model | one explicit model value passed identically to every run (value OPEN, §12); model reported by the CLI recorded per run |
| Auth / billing | persisted Claude.ai Pro login; invoked via `claude_sanitized`; no API key, no other provider |
| CLI flags | identical flag set (except C2 phase-specific ones, §8) |
| Permission mode & tool allowlist | identical for C0, C1 and C2 phase 2 (value OPEN); C2 phase 1 differs only as specified in §8 |
| Sandbox / settings | byte-identical settings; hash recorded per run |
| Network | agent has no network access during runs |
| Fixture | identical pristine fixture per task (same hash) |
| Task statement | identical bytes per task across configurations |
| Prompt delivery | identical method (argument vs stdin: OPEN, but one method for all) |
| Wall-clock cap | one cap for all runs; for C2 it applies to the **sum** of both phases (value OPEN) |
| Turn cap (if any) | if used, identical; for C2 applied to the total (OPEN whether used at all) |
| Other instruction sources | none: no user-level / managed / ancestor-directory CLAUDE.md, rules, skills, agents, commands, plugins, hooks, MCP servers, output styles |
| Dependencies | identical pre-installed dependency state per task (§4) |

### 3.2 Configurations

**C0 — baseline.** The envelope above. The working copy contains no
`CLAUDE.md`, `CLAUDE.local.md`, `.claude/` instruction content or equivalent
from the experiment. The agent receives the task statement only.

**C1 — repository instructions.** C0 plus exactly one benchmark `CLAUDE.md` at
the working-copy root, present from the first moment of the run and included in
the fixture's single baseline commit (§4).

- Its content is written once, is version-controlled, and has a recorded hash.
- It MUST NOT contain task solutions, hints about the specific defect or
  feature, hidden-test information, or reference-implementation details.
- Default: **one byte-identical file for all six tasks.** Whether a per-language
  variant restricted to genuine repository-level facts (e.g. how the test suite
  is invoked) is allowed is **OPEN**; if allowed, the rule is "identical across
  all tasks of one language, differing only in the named repository-level
  fields", and it must be decided before the content is written.
- The file is frozen before the first final run and not revised based on
  final-run results.

**C2 — explicit planning workflow.** C1 (same CLAUDE.md) plus a two-phase run in
one session: a read-only planning phase started with the task statement
embedded in a fixed planning wrapper, then a fixed, pre-written approval
message that continues the same session into implementation with C0/C1's
permissions. Full contract in §8.

### 3.3 Only intended treatment differences

| | C0 | C1 | C2 |
|---|---|---|---|
| Benchmark CLAUDE.md | — | yes | yes (same as C1) |
| Planning wrapper around task statement (fixed text) | — | — | yes |
| Read-only phase 1 | — | — | yes |
| Fixed approval message + same-session continuation | — | — | yes |

The planning wrapper and approval message are **part of the C2 treatment**, not
a prompt difference that breaks comparability. The task statement itself is
byte-identical inside all three. Anything else that differs between
configurations is a protocol violation.

## 4. Clean-run contract

**Pristine fixture.** Each task has one pristine fixture repository, stored
outside every agent-readable location, with a recorded content hash. Separate
C0 and C1/C2 variants differ only by the treatment `CLAUDE.md`.

- The fixture's git history is a **single neutral baseline commit** (fixed
  author, date and message; identical form across tasks and configurations).
  It MUST NOT contain the reference solution, solution history, branches, tags,
  stashes, reflog entries or notes that reveal it.
- Whether the working copy is a git repository at all is fixed per protocol:
  yes, with that single commit (so the agent sees a normal repository);
  mechanism details are harness work.

**Per-run working copy.** Created fresh for each run (each attempt) from the
pristine fixture; used by exactly one run; never reused.

- Its path is **opaque**: it MUST NOT encode task ID, configuration, repetition
  or any hint (e.g. a random token under a fixed parent). Path shape is
  identical across configurations.
- The working copy is the agent process's working directory and the only
  location it may write (besides what the CLI itself needs, below).
- No ancestor directory of the working copy may contain `CLAUDE.md` or other
  instruction files; the harness checks this before each run and refuses to
  start otherwise.

**HOME / user.** All runs execute as `cclab` with HOME `/home/cclab`, via
`claude_sanitized`, with `DISABLE_AUTOUPDATER=1`. The user-level and managed
instruction/config locations are verified empty or absent before each run
(extending the `setup/20-verify.sh` isolation checks).

**No state carryover.** Nothing produced by one run may be visible to any later
run. This covers:

- working-copy files (solved by fresh copies);
- Claude Code's per-project state under `~/.claude` (session transcripts,
  auto-memory) and in `~/.claude.json`: the working-copy path is unique, but
  earlier runs' transcripts still sit under HOME. The mechanism that keeps them
  unreadable from later runs is **OPEN** (candidates: archive-and-remove after
  each run; sandbox/permission deny rules on those paths; disabling auto-memory
  via a setting verified to exist in 2.1.263). Required outcome regardless of
  mechanism: a pilot probe confirms that a run cannot read another run's
  transcript or memory;
- shell history, temp directories (`/tmp` entries created by a run are removed
  or isolated; mechanism OPEN).

**Generated caches and dependencies.** The agent has no network, so all
dependencies needed to build and test (Node `node_modules`, the Python
environment incl. pytest) are prepared **before** the agent starts, identically
for every configuration of a task, and are either part of the pristine fixture
or reproduced from a lockfile offline (mechanism OPEN). Caches that tests or
tools generate (`__pycache__`, `.pytest_cache`, `*.tsbuildinfo`, `dist/`,
coverage output, etc.) are excluded from diffs by a fixed, per-language ignore
list frozen with the tasks. The ignore list MUST NOT hide source or test files.

**How a run ends.** A run's agent phase ends at the first of:

1. the `claude -p` process exits by itself (for C2: the implementation-phase
   process; or phase 1 if the run cannot continue, §8);
2. the wall-clock cap expires → the harness terminates the process tree;
3. a harness-detected infrastructure fault (§10).

After the end, the harness records the exit status, confirms that no agent
process remains, snapshots the final working copy, and only then may the
evaluator start (§6). The agent is never re-invoked in the same run to "finish
up".

## 5. Agent information boundary

**Claude may see:**

- the repository-under-test (the per-run working copy, including its single
  baseline commit and any **public** tests shipped in the fixture);
- the public task statement for that task;
- the treatment material of its own configuration (C1/C2: the `CLAUDE.md`;
  C2: the planning wrapper and approval message);
- the installed toolchain and read-only system locations the sandbox allows.

**Claude MUST NOT see (through any tool surface — Bash, Read/Edit/Write,
Glob/Grep, or any other):**

- hidden acceptance and regression tests;
- reference solutions;
- the scorer / evaluator implementation and configuration if they reveal
  hidden expectations (default: all of it is hidden);
- task authoring notes, pilot material, the run-order file, the results store;
- outputs, transcripts, diffs or memory from previous repetitions or other
  configurations;
- other tasks' fixtures;
- credentials, and `/mnt/c` (kept hidden as verified during setup).

Enforcement: hidden material is stored outside the working copy. **Preferred:**
unreadable by `cclab` at the OS permission level during agent runs;
**minimum:** denied by the sandbox for every tool surface. The choice is
**OPEN**, and whichever is used MUST pass a pilot leak probe that attempts to
read each hidden location through each tool surface (per
`setup/NEXT-behavioral-checks.md` §6 style) before final runs.

Public task statements MUST NOT describe the hidden tests beyond what a normal
issue/feature request would state.

## 6. Acceptance / scoring boundary

**A. Agent execution** (§4, §8) produces only: the final working-copy state, the
process records and the CLI output. The agent's own claims ("done", "all tests
pass") are recorded as text but are **never** a success signal.

**B. Independent evaluator execution** starts only after A has ended and no
agent process remains. The evaluator:

- operates on a **copy** of the final working-copy snapshot, never in place;
- restores each task's **protected paths** (hidden tests, test configuration
  files, test-runner scripts / package.json test entry, conftest-like hooks —
  listed per task and frozen with it) to their pristine versions and adds the
  hidden tests;
- runs a fixed test command with a fixed timeout, without network, in a
  sandbox that cannot write outside its evaluation copy (agent-written code
  executes during tests and must not be able to touch the results store);
- is deterministic: validated in pilot by repeated runs on the reference
  solution (§9).

**Conceptual status axes** (recorded separately, never merged into a weighted
score in V0):

| Axis | Values |
|---|---|
| Agent process | `completed` · `error_exit` · `timeout` · `limit_interrupted` · `auth_failure` · `harness_error` |
| Run validity | `valid` · `invalid:<reason>` (§10) |
| Acceptance tests | `pass` · `fail` · `error` · `not_run` |
| Regression tests | `pass` · `fail` · `error` · `not_run` |
| Integrity | `clean` · `protected_path_modified` · `out_of_tree_write_detected` |
| C2 protocol (C2 only) | `ok` · `phase1_write` · `phase_transition_failed` (§8) |

**Resolved** (the V0 primary binary outcome) = `valid` ∧ acceptance `pass` ∧
regression `pass` ∧ integrity `clean`. No composite or weighted score is
defined in V0.

Integrity violations by the *agent* (e.g. editing hidden-test-equivalent public
tests or test configuration) are **outcomes** — the run is valid and not
resolved — not invalid runs. They are reported explicitly.

**Validity is classified from agent-phase evidence only (process status,
harness logs, leak/integrity preconditions), and is recorded before the
evaluator is started for that run.** This keeps any later rerun decision independent of the
outcome (§10).

**Task validity gate.** Before a task is frozen:

- hidden **acceptance** tests MUST fail on the pristine fixture (bug fix,
  feature) and pass on the reference solution;
- hidden **regression** tests MUST pass on both the pristine fixture and the
  reference solution;
- both MUST give the same result over repeated evaluator runs (determinism).

For a **refactor** task, the regression tests pass on both pristine and
reference, so they cannot on their own detect success: a no-op would pass. Each
refactor task therefore needs an **objective acceptance check of the stated
structural change** (e.g. a hidden structural test). Its exact form is
**OPEN** and must be defined and validated before the task is frozen.

## 7. Run artifacts

Every attempt preserves at least:

| Group | Fields |
|---|---|
| Identity | run ID (unique per attempt), cell ID (task × config × repetition), attempt number, task ID, language, task type, configuration, repetition |
| Timing | start/end timestamps (UTC) of the run and of each C2 phase, harness gap between phases, wall-clock durations |
| Process | agent exit code(s), termination cause (self-exit / cap / fault), signal if killed |
| Output | CLI stdout/stderr or structured output (e.g. JSON / stream-JSON) where it contains no secrets; session ID(s) |
| Repository | final diff against the pristine snapshot (not against in-repo git), changed-file list (added / modified / deleted), ignore list applied, final-tree hash |
| C2 | pre/post phase-1 tree hashes, phase-1 plan text, approval message hash, same-session evidence |
| Evaluation | evaluator version/hash, test commands, per-test results, exit codes, evaluator stdout/stderr, all status axes (§6) |
| Validity | validity class, invalid-run reason, time of classification (before scoring) |
| Provenance | Claude Code version, model value requested and model reported, Node/npm/sandbox-runtime/Python versions, settings hash, CLAUDE.md hash (C1/C2), task-statement hash, planning-wrapper hash (C2), fixture hash, harness version/hash, run-order file hash, host kernel release |
| Environment | names (never values) of variables removed by `claude_sanitized`; `DISABLE_AUTOUPDATER` value |
| Auth context | only `loggedIn`, `authMethod`, `apiProvider`, `subscriptionType` if captured |

**Usage / token fields.** No specific metric is assumed. During harness
implementation, the installed CLI's actual output (e.g. in the structured
output format) must be inspected; only fields that are **actually present and
stable across pilot runs** are recorded, with their names exactly as emitted and
a note on what they mean for a subscription login. Missing fields are recorded
as absent, not estimated.

**Never stored:** credentials, token values, environment values of any
auth-related variable, account email / org IDs, contents of
`~/.claude/.credentials.json` or `~/.claude.json`.

Artifacts are written outside the agent-readable area (§5) and are append-only
once the run is classified.

## 8. C2 two-phase contract

**Planning (phase 1).** A single headless invocation, starting a new session,
whose input is the fixed planning wrapper containing the unmodified task
statement. The wrapper instructs Claude to inspect the repository and produce an
implementation plan, and not to modify anything. Its text is written later,
fixed across all C2 runs and tasks, frozen before final runs, and contains no
task-specific or solution content. The plan is Claude's own; no human edits,
approves selectively, corrects or supplements it.

**Read-only** means, for the whole of phase 1:

- the working-copy tree is unchanged: content hash of the working copy after
  phase 1 equals the hash before it, excluding **only** the frozen
  generated-cache ignore list of §4 (so a permitted inspection command that
  merely writes e.g. `__pycache__` is not a violation — whether running tests in
  phase 1 is permitted at all depends on the enforcement mechanism, O1);
- no writes elsewhere outside the CLI's own session state;
- no state-changing commands (installs, git commits/branch changes, file
  creation in temp dirs used for the task, network access).

Reading files, searching and running side-effect-free inspection commands are
allowed within the same sandbox as C0/C1, except that the working copy is
read-only in phase 1 (that difference is the treatment).

**Enforcement mechanism — OPEN.** Candidates: restricting write-capable tools
for phase 1, a permission mode that forbids edits, a read-only sandbox view of
the working copy, or a combination. Using the built-in plan permission mode as
the *mechanism* is permitted if the pilot shows it meets the read-only
definition and allows same-session continuation; the experimental claim remains
"explicit planning workflow", never "Plan Mode". The chosen mechanism, and the
evidence that it works, are documented separately from the research claim.
Regardless of mechanism, the harness **verifies** read-only via the tree hash.

**Same session.** Phase 2 continues the *same* Claude session (same session ID,
full phase-1 context including the plan). The exact CLI mechanism (e.g.
resuming by session ID in headless mode, and whether permissions can be changed
at that point) is **OPEN** until piloted. If the pilot shows same-session
continuation with changed permissions is impossible, that is a design change
requiring an explicit, recorded decision — not a silent fallback to a fresh
session or to pasting the plan into a new prompt.

**Fixed approval message.** Phase 2 is started by one pre-written approval /
continuation message, byte-identical across all C2 runs and tasks, frozen
before final runs, containing no feedback, hints or reference to the content of
the particular plan. It is sent regardless of the plan's quality (even an empty
or poor plan is approved). No other human or harness message is inserted.

**Transition.** Phase 1 ends when its process exits. The harness then checks
the tree hash, records the phase-1 outputs, and immediately starts phase 2 with
the implementation permissions, which MUST equal C0/C1's. Nothing is changed in
the working copy between phases.

**Duration.** Recorded per phase plus the harness gap. The primary duration is
phase 1 + phase 2 (agent time). The single wall-clock cap (§3.1) covers the
total of both phases; if the cap expires in phase 1, phase 2 is not started and
the run ends as `timeout`. Whether phase 1 additionally gets a sub-cap is
**OPEN**; if one is introduced it is fixed for all C2 runs.

**C2 protocol violations:**

| Condition | Classification |
|---|---|
| Working-copy tree changed during phase 1 | `phase1_write` → invalid (treatment not delivered) |
| Phase 2 not in the same session, or context lost | `phase_transition_failed` → invalid |
| Approval message differs from the frozen text, or any extra message injected | invalid |
| Phase-2 permissions differ from C0/C1 | invalid |
| Write attempt in phase 1 blocked by enforcement | not a violation; recorded |
| Phase 1 produces no usable plan but exits normally | not a violation; approval is still sent; recorded |

Because C2 is compared to C1 at equal total budget, C2 also measures the time
spent on planning. That is part of the workflow's cost and is reported, not
corrected away.

## 9. Pilot vs final runs

**Pilot tasks** have distinct IDs (e.g. `P-…`), are authored separately from
the 6 final tasks, and:

- are **excluded** from all final results and from any aggregate;
- may be used to debug the harness, calibrate timeouts / caps, test session
  continuation and C2 enforcement, test the evaluator and its determinism, run
  leak probes and state-carryover probes, and inspect CLI output fields;
- MUST NOT be promoted into the final benchmark after their internals or
  results have influenced design;
- have their results stored separately, labelled pilot.

Running the **final tasks** through the harness before the freeze is limited to
the task validity gate (§6: evaluator on pristine and reference) and dry runs
that do **not** invoke the agent. Agent runs on final tasks before the freeze
would let final-task results shape the design; if one happens anyway, it is
recorded and disclosed and its result is not a final run.

**Frozen before the first final run** (all with recorded hashes/versions):

- the 6 final tasks: fixtures, public statements, hidden tests, reference
  solutions, protected-path lists, ignore lists, refactor structural checks,
  validity-gate evidence;
- C1 `CLAUDE.md`; C2 planning wrapper and approval message;
- model value, CLI flags, permission mode, tool allowlist, settings, sandbox
  configuration, prompt delivery method;
- wall-clock cap (and C2 sub-cap / turn cap if any);
- harness and evaluator versions;
- run order and seed (§11);
- invalid-run and rerun policy (§10);
- the list of usage fields to record, and the analysis/reporting plan.

After the freeze, any change requires a protocol amendment; runs before and
after a material amendment are not pooled.

## 10. Invalid-run policy

**Experimental outcomes (valid runs, counted):**

- Claude attempts the task and the evaluator reports failure;
- Claude exits early, gives up, or claims success wrongly;
- `timeout` at the wall-clock cap (the cap is part of the envelope);
- `error_exit` caused by the agent's own behavior within a working
  environment;
- integrity violations by the agent (§6).

**Invalid runs (not counted as task outcomes; reason recorded):**

| Cause | Class |
|---|---|
| Auth failure / service outage / 401 / server-side error unrelated to the task | `invalid:infrastructure` |
| Harness crash, bug, or wrong configuration applied | `invalid:harness` |
| Corrupted or wrong fixture (hash mismatch) | `invalid:fixture` |
| Hidden tests, reference solution or other runs' outputs were accessible or accessed | `invalid:leak` |
| State carryover detected (e.g. leftover files, foreign transcripts readable) | `invalid:carryover` |
| C2 protocol violation (§8) | `invalid:c2_protocol` |
| Pre-run environment check failed (instruction sources, versions, sanitized env) | run not started; logged as `preflight_failed` |

**Subscription limit** interrupting a run is its own class,
`limit_interrupted`. It is **not** a task failure and **not** silently
dropped. The run is not continued under any other billing mechanism, and not
resumed mid-session after the limit resets. Execution of the order pauses until
the limit resets. How to detect it reliably from CLI output is **OPEN** (pilot).

**Rerun policy — OPEN, with fixed constraints.** Whether and how many times an
invalid or `limit_interrupted` cell is re-attempted is not yet decided. Any
policy adopted MUST:

- trigger only on an invalidity class, never on an evaluator result;
- be decided from agent-phase evidence recorded before scoring (§6);
- re-attempt the same cell from a fresh working copy and a new session, with a
  new run ID and incremented attempt number;
- keep and report every attempt;
- define in advance what happens when a cell cannot obtain a valid attempt
  (reported as missing, never imputed).

Any `invalid:leak` or `invalid:carryover` also triggers a review of whether
other runs were affected, before continuing.

## 11. Randomization and order effects

**Risk.** Running always C0 → C1 → C2, or all repetitions of one cell
together, confounds configuration with time: model/service changes across
days, time-of-day load, Pro usage windows (a limit reset splits the schedule),
harness fixes made mid-campaign, and operator attention. A configuration run
consistently "later in the window" or "after a limit reset" would absorb those
effects.

**Strategy (to be generated before the freeze, not now):**

- **Blocking by repetition:** 3 blocks; each block contains each of the 18
  `(task, configuration)` cells exactly once. Block *r* holds repetition *r*.
- **Within-block order:** a uniformly random permutation of the 18 cells, drawn
  with a documented pseudo-random generator from a seed recorded in the
  protocol freeze; each block uses its own derived permutation.
- Optional constraint (decide before generation, **OPEN**): avoid the same task
  in consecutive positions; if applied, implemented by a documented,
  seed-deterministic procedure, not by hand.
- Blocks run in order 1 → 2 → 3; the full 54-entry order file is committed and
  hashed before the first final run.
- **Non-adaptive:** the order is never changed based on results. A limit pause
  or infrastructure pause resumes at the next unexecuted position. Re-attempts
  of invalid cells (if the rerun policy allows them) are scheduled by a rule
  fixed in advance (e.g. appended at the end of the current block), not
  chosen by hand.

## 12. Frozen vs open decisions

### FROZEN FOR V0

| # | Decision |
|---|---|
| F1 | Design: 6 final tasks (Py/TS × bug fix / small feature / refactor) × C0/C1/C2 × 3 repetitions = 54 runs |
| F2 | Environment and versions as verified in setup; `cclab` user; persisted Claude.ai Pro login; `claude_sanitized`; `DISABLE_AUTOUPDATER=1`; no API key / other provider / paid fallback |
| F3 | Treatments: C1 = C0 + one fixed repository `CLAUDE.md`; C2 = C1 + read-only planning phase + fixed approval message + same-session implementation |
| F4 | C2 is described as an explicit planning workflow, not as a benchmark of the built-in plan mode |
| F5 | Identical implementation envelope for C0, C1 and C2 phase 2 (§3.1); C2 phase 1 differs only in the read-only planning treatment (§8); all other conditions identical; C2's cap covers both phases in total |
| F6 | Task statement byte-identical across configurations; planning wrapper and approval message are C2 treatment |
| F7 | Fresh per-run working copy from a pristine fixture at an opaque path; single neutral baseline commit; no cross-run session reuse |
| F8 | No instruction sources other than the treatment file (user, managed, ancestor directories checked before each run) |
| F9 | Hidden tests, reference solutions, scorer, results and other runs' outputs unreadable by the agent through every tool surface; verified by leak probe |
| F10 | Evaluator runs only after the agent ends, on a copy, with protected paths restored, sandboxed, no network |
| F11 | Separate status axes; binary "resolved" as primary outcome; no weighted composite score |
| F12 | Validity classified from agent-phase evidence before evaluator results are seen |
| F13 | Agent self-report is never a success signal; integrity violations by the agent are outcomes, not invalid runs |
| F14 | Diff computed against the out-of-sandbox pristine snapshot |
| F15 | Usage fields recorded only if actually emitted and stable; no secrets ever stored |
| F16 | Pilot tasks separate, excluded, never promoted |
| F17 | Blocked-by-repetition, seeded within-block random order; non-adaptive |
| F18 | `limit_interrupted` is its own class; never continued under another billing mechanism |
| F19 | Reporting is descriptive and per task; no generalization beyond these tasks / versions / dates |

### OPEN BEFORE HARNESS IMPLEMENTATION (or before the freeze, as noted)

| # | Open question | Blocks | Resolution path |
|---|---|---|---|
| O1 | C2 phase-1 read-only enforcement mechanism (tool restriction / permission mode / read-only sandbox view) | C2 harness | technical pilot on a pilot task; verify with tree hash |
| O2 | C2 same-session continuation mechanism in headless mode, and whether permissions can change between phases | C2 harness | technical pilot; if impossible → explicit design decision |
| O3 | Preventing cross-run access to `~/.claude` transcripts / auto-memory / `~/.claude.json` state | harness | inspect 2.1.263 behavior; carryover probe |
| O4 | Where hidden material lives and how it is made unreadable (OS permissions vs sandbox deny) | harness | leak probe across all tool surfaces |
| O5 | Model value to pin, and whether the CLI reports the model actually used | harness | inspect CLI; record reported model |
| O6 | Permission mode and tool allowlist for C0/C1/C2-implementation under headless operation inside the sandbox | harness | pilot: agent can edit and run tests; nothing else loosened |
| O7 | Prompt delivery method (argument vs stdin) and structured output format | harness | inspect CLI |
| O8 | Available and stable usage/token fields | artifact schema | inspect CLI output across pilot runs |
| O9 | Dependency preparation (node_modules, Python env) without agent network access; cache ignore lists | fixtures | pilot per language |
| O10 | Temp-directory isolation / cleanup between runs | harness | pilot |
| O11 | Reliable detection of subscription-limit interruption and of auth/service failures from CLI output | invalid-run classification | pilot observation; never provoke limits deliberately beyond normal use |
| O12 | Wall-clock cap value; whether to use a turn cap; whether C2 phase 1 has a sub-cap | freeze | pilot timing on pilot tasks only |
| O13 | Rerun policy for invalid / limit-interrupted cells (within §10 constraints) | freeze | decide before first final run |
| O14 | CLAUDE.md scope: one byte-identical file vs per-language repository-level variant | C1 content | decide before writing it |
| O15 | Objective structural acceptance check for refactor tasks | task freeze | define per refactor task; validate on pristine vs reference |
| O16 | Optional order constraint (no same task in consecutive positions) | order generation | decide before generating the order |

Amendment note: O3 and O4, **for the credential portion**, are resolved by Amendment A1
(§13). The rest of O3 (transcript / auto-memory carryover) and O4 (hidden tests / reference /
evaluator material) stay open. The run-artifact schema (§7) is now specified by the manifest
contract in `docs/RUN_MANIFEST_V0.md`.

Status note (2026-09-27, no decision changed): O1, O2, the cleanup part of O3, the canary boundary
of O4, O6 and O7 were settled *for the harness* by `docs/HARNESS_READINESS_SPIKE.md` (decision
table) and exercised by `docs/HARNESS_WSL_SMOKE.md`; they still need confirmation on real pilot
tasks. The table above is kept as written. Pilot-phase status of every O-item is tracked in
`docs/PILOT_PLAN.md` §19.

---

## 12a. Amendment A2 — neutral baseline and treatment state (2026-09-27)

- **Neutral baseline (supersedes the "included in the fixture's single baseline commit" wording
  of §3.2 and §4 for the treatment file).** The single baseline commit contains only the pristine
  task fixture. It is identical for C0, C1 and C2, and deterministic. The C1/C2 `CLAUDE.md` is
  placed in the working copy after that commit and stays uncommitted, so no configuration has its
  own history.
- **Treatment-state invariant.** Instruction material (`CLAUDE.md`/`CLAUDE.local.md` at any
  depth, anything under `.claude/`) must equal the frozen treatment at agent start and be
  unchanged at agent end. Otherwise the run is `invalid:treatment_drift` (§3.3: any unintended
  difference between configurations is a protocol violation).
- **Open finding G11** (`docs/PILOT_PLAN.md` §15): under the current envelope
  (`--setting-sources ""`) the installed CLI most likely does not load the repository `CLAUDE.md`
  at all. Until this is resolved, a C1/C2 run cannot be claimed to have received the §3.2
  treatment.

## 13. Amendment A1 — V0 credential-isolation execution boundary (2026-09-25)

This amendment records the accepted V0 execution boundary established by the
credential-isolation spikes. Evidence: `docs/CREDENTIAL_ISOLATION_SPIKE.md` (Candidate 1,
NO-GO) and `docs/CREDENTIAL_ISOLATION_CANDIDATE2.md` (Candidate 2, GO). It resolves the
credential portion of O3/O4 and does not change the research question, treatments, or any other
frozen decision.

### 13.1 Trusted Claude CLI

The trusted Claude CLI may access the persisted Claude.ai authentication state required for Pro
login. The outer sandbox **intentionally permits the Unix-socket capability** required for
Claude Code's inner Bash sandbox to initialize (on Linux this is the coarse
`allowAllUnixSockets` control — there is no path-scoped alternative). The outer sandbox alone is
**not** sufficient credential isolation; the inner sandbox and the built-in permission rules are
the credential boundary for model-controlled tools.

### 13.2 Model-controlled Bash / subprocesses

Model-controlled Bash and its child processes run under Claude's inner sandbox. Candidate 2
behaviorally demonstrated, on a synthetic fake-credential fixture:

- fake-credential read denial from Bash;
- Python `open()` and Node `fs.readFileSync` read denial (OS-level EACCES);
- AF_UNIX re-confinement (socket creation blocked inside the inner sandbox);
- WSL Windows-interoperability blocking (no `cmd.exe`/interop launch; the AF_UNIX block, not
  merely PATH absence, prevents the interop route);
- host-socket blocking (a live host canary listener received zero connections);
- no observed unsandboxed fallback (`dangerouslyDisableSandbox` still denied);
- allowed workspace operations still work (read/edit/write and harmless subprocesses succeed).

Operating requirements carried by this boundary: the inner settings must grant
`sandbox.filesystem.allowWrite` for the working copy and TMPDIR, and each working copy must be
pre-seeded with empty `.claude/settings.json` and `.claude/settings.local.json`, or Claude's
Bash-tool sandbox fails to start commands. Those seeded files are agent-writable but, as
Candidate 2 showed, cannot weaken protection (operator posture wins; `--setting-sources ""`
excludes them).

### 13.3 Built-in file tools

Credential protection for the built-in file tools uses Claude permission rules, applied
separately from the Bash sandbox. Observed in 2.1.263:

- **Read**: hard denial (permission rule).
- **Edit**: hard denial (permission rule).
- **Write**: protected through the supported mechanism; in 2.1.263 a `Write(path)` deny rule is
  inert and only `Edit(path)` is consulted, so protection is expressed via `Read()`/`Edit()`
  rules plus the directory deny — no unsupported `Write(path)` semantics are assumed.
- **Grep / Glob**: weaker, best-effort enforcement (the denied path is silently skipped with no
  error). Reported honestly as best-effort, not an OS-level guarantee.

### 13.4 Real credential file

The real credential path was configured under the same loaded protection policy as the fake
fixture, while the real file itself remained unread and unchanged. This is
**structural / policy-equivalence evidence**, not direct testing of the real secret's contents
and not an absolute security proof.

### 13.5 C0 / C1 / C2 equality

The Candidate-2 credential controls are common environment controls for the C0 implementation,
the C1 implementation and the C2 phase-2 implementation. C2 phase 1 differs only for its
intended read-only planning treatment. Credential isolation is never an experimental variable.
