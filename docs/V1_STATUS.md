# CodeAgent ConfigLab — V1 Status

A concise statement of what the V1 harness currently provides, and what it does not yet contain.
See `docs/PILOT_V1_CLOSEOUT.md` for the pilot run that exercised this machinery end to end.

## What V1 provides

- **Deterministic series execution** — a frozen spec + seed produces one deterministic six-cell
  schedule (`series.py: build_spec`, `generate_schedule`); re-generating from the same frozen spec
  and seed always yields the same order, independent of any run's outcome.
- **C0/C1/C2 treatment isolation** — C0 (no instruction material), C1 (one frozen `CLAUDE.md`),
  and C2 (the same `CLAUDE.md` plus a frozen planning wrapper and approval message) are enforced
  structurally, not just by convention (`treatment.py`, preflight checks, per-attempt
  `treatment.json` verification).
- **Explicit C2 planning/continuation workflow** — a read-only planning phase, verified
  post-hoc (working-copy and Claude-project-state snapshot diff), followed by a fixed approval
  message that resumes the *same* session into an implementation phase using the identical
  envelope C0/C1 use (`orchestration.py: run_agent_condition`).
- **Requested/observed model provenance** — the model actually used is read only from the CLI's
  structured `system`/`init` stream-json event, never from assistant text or stderr; any
  requested/observed mismatch fails the attempt closed (`invalid:harness`), independently per C2
  phase.
- **Timeout / process-tree control** — a real wall-clock deadline per attempt (shared across both
  C2 phases, never reset), enforced by terminating the entire process group and confirming no
  survivors, never fabricating a return code on a cap (`process_control.py`).
- **Agent sandbox** — the agent process runs under a scoped outer/inner sandbox policy restricting
  filesystem and network access (`envelope.py`, `policy` rendering in `runners.py`).
- **Evaluator sandbox** — task evaluation runs strictly after the agent process has exited, on a
  throwaway copy, with hidden tests injected only into that copy and a narrow deny-by-default read
  policy (credentials, the pristine fixture, and hidden test sources are all explicitly denied)
  (`evaluator_sandbox.py`, `task_evaluator.py`).
- **Hidden/reference isolation** — hidden tests and reference solutions are never copied into any
  artifact directory the agent or a later report can read; a secret-marker scanner on every
  written artifact is a defense-in-depth backstop, not the primary isolation mechanism
  (`artifacts.py`).
- **Deterministic evaluator** — acceptance/regression/structural checks run in a scope-guarded
  sandbox with a fixed toolchain identity (`evaluator_sandbox.py`'s `g5s-v2`), generated build
  outputs (e.g. `dist/**`) stripped before every check so they can never mask real changes.
- **Run validity vs. analysis eligibility** — two independent axes: whether an attempt is a valid
  observation at all (`run_validity`) versus whether it's countable in analysis
  (`analysis_eligibility`), derived by one canonical rule (`status.py:
  derive_analysis_eligibility`) — a task failure is still a valid, countable observation.
- **Replacement / re-evaluation policy** — at most one operator-approved replacement per cell for
  a fixed set of infrastructure-class validity outcomes, never automatic; re-evaluation re-runs
  only the evaluator against a preserved final working copy, never a new agent attempt
  (`series.py: approve_replacement`, `reevaluate`).
- **Append-only series history** — every state transition (attempt start/finish, replacement
  approval, re-evaluation, cleanup remediation, halt, resume) is one line in an append-only event
  log; cell state is always *derived* from that log, never stored separately, and no event is ever
  edited or deleted (`series.py: Series._append`, `Series.cells`).
- **Safe artifact finalization** — a fixed artifact allowlist, secret-scanned writes that are
  withheld (never silently dropped or fatally erroring) when they trip the scanner, and a
  required-evidence rule that fails an attempt closed if its `manifest.json`/`result.json`
  couldn't be persisted at all (`artifacts.py`, `lifecycle.py: _finalize`).
- **Real cleanup + residue verification** — production execution always uses a real, scope-guarded
  cleanup runner (never silently falls back to a no-op); a post-cleanup residue check verifies
  every scoped target actually disappeared, and a real cleanup that fails or leaves residue fails
  the attempt closed (`cleanup.py: verify_residue`, `lifecycle.py: _finalize`).
- **Recoverable vs. hard-stop halt semantics** — genuine safety hard-stops (leak, carryover, C2
  phase-1 write) remain permanently non-resumable; a recoverable operator-review halt (e.g. a
  cleanup-wiring incident, once remediated and verified) can be explicitly, auditably resumed via
  one new append-only event, never by editing history (`series.py: halted`, `resume`,
  `_halt_category`).
- **Python and TypeScript task support** — the task-package/evaluator machinery is
  language-agnostic in practice, demonstrated by one Python task (P-PY-01) and one TypeScript task
  (P-TS-01) sharing the identical harness pipeline.
- **Pilot execution evidence** — a full real pilot run (six planned cells, one replacement, two
  real C2 two-phase attempts) exercising every mechanism above end to end; see
  `docs/PILOT_V1_CLOSEOUT.md`.

## What V1 does not yet contain

- The **final six-task benchmark set** (the pilot's two tasks are instruments, not final tasks).
- The **final 54-run dataset**.
- A **frozen harness implementation snapshot** for the final benchmark — the harness changed
  during the pilot (see `docs/PILOT_V1_CLOSEOUT.md` §4.3) and must be frozen before the 54-run
  benchmark begins.
- Any **final comparative results or report** across configurations — the pilot deliberately draws
  no such conclusion (see `docs/PILOT_V1_CLOSEOUT.md` §6).
