# Pilot-v1 Closeout

Status: **pilot-v1 complete**. This document records what was run, what it found, and what it
proved — reconstructed strictly from the frozen `spec.json`/`schedule.json` and the append-only
`events.jsonl` under the series root, cross-checked against every attempt's own
`manifest.json`/`result.json`/`c2.json`/`cleanup.json`.

## 1. Scope

This pilot covers exactly:

- Task packages: **P-PY-01** (Python, bugfix) and **P-TS-01** (TypeScript, refactor)
- Configurations: **C0**, **C1**, **C2** (see `docs/EXPERIMENT_PROTOCOL_V0.md` §3.2–3.3 for the
  full definitions)
- One planned repetition per (task, configuration) pair — six planned cells total

**These two tasks are pilot instruments, not part of the final benchmark.** The final benchmark
taskset (a separate, larger six-task set intended to produce 54 runs) has not yet been authored.
Nothing in this pilot's task content, wording, or outcomes is reused as a final benchmark task.

## 2. Frozen execution design

Identities below are read directly from the frozen files, not copied from any prior discussion.

| Value | Frozen identity |
|---|---|
| `spec_hash` | `90628ef77d385c98ed5ee8ec1f7c6e9a709da91c6cb11c2cdff5ccb0736b4b81` |
| `schedule_hash` | `ebd175cddd622153138323d8116a06e001650f96960cf03bd16de1a5bd04bfe9` |
| Requested model | `claude-sonnet-5` |
| Effort | `high` |
| Agent timeout (C0/C1; C2 shared budget) | `900` seconds |
| Frozen `CLAUDE.md` hash (C1 and C2) | `213df66805a816a4dea6998580fd85c91c3d3a1beb08acb3dbdf7ddc000e0541` |
| Frozen planning-wrapper hash (C2) | `299b08446b440345a7f177258208c3bf8b1d33addc3934ed1356bb72a0c47fc4` |
| Frozen approval-message hash (C2) | `dbf445a514ca2ae9576935d09d7add9cf9157f88ca01ae1388d65a1f1009ee14` |
| Order seed | `configlab-pilot-v1-order` → derived integer `17271757` |

**C2 shared-deadline semantics**: a C2 attempt is one run, two Claude CLI invocations, sharing a
single 900-second wall-clock budget. Phase 1 (planning) gets the full budget; the time spent
verifying phase 1 was read-only is *not* charged; phase 2 (implementation) receives whatever
remains, via a fresh `Deadline` seeded with that remainder — never a reset to a full 900 seconds.
Both real C2 attempts in this pilot confirm this: phase 2's recorded budget was `878.39s` and
`886.02s` respectively, never `900.0s`.

Both task packages' validity gates were `PASS` at freeze time and their live hashes matched the
frozen spec at every execution in this pilot (re-verified before each attempt).

## 3. Pilot execution history

All six planned cells reached a countable main observation. Ordered by schedule position:

| Pos | Cell | Task × Config | Attempt(s) | Effective result |
|---|---|---|---|---|
| 1 | `cell-fe764020303430fd` | P-TS-01 × C0 | see §3.1 below | countable, via replacement |
| 2 | `cell-be645426fc613334` | P-PY-01 × C1 | `run_h6yqfryfc4ag3sofydchma52su` | valid / countable |
| 3 | `cell-e5edb916959ba3d7` | P-TS-01 × C2 | `run_5kykwbnvc62g6id62mgspzvvdy` | valid / countable |
| 4 | `cell-af7114946671407f` | P-PY-01 × C2 | `run_weazub5qcxph7ako6kbc7so7a4` | valid / countable |
| 5 | `cell-c2708598bbb89ec1` | P-TS-01 × C1 | `run_7iq76hubytpgiojjo736yxlz2q` | valid / countable |
| 6 | `cell-7bb8b30547dbb18c` | P-PY-01 × C0 | `run_xwuhkqj72gpeksaztork23oscy` | valid / countable |

Every attempt above passed acceptance and regression; every real (non-Dry) cleanup performed and
verified all scoped residue clear.

### 3.1 Cell 1 — original and replacement, kept distinct

Cell 1 required the series' one permitted replacement. Both attempts remain on record,
side by side, exactly as the append-only event log requires — neither is rewritten or removed:

- **Original attempt** `run_chl55f5gx6o7naprqdj33i24ou` (ordinal 1) — historical. Its agent and
  evaluator phases completed and passed acceptance/regression, but its production cleanup step
  silently used a no-op dry runner (see §4.1). Effective status, via the append-only
  `cleanup_remediated` correction event (never a rewrite of the attempt's own `result.json`):
  **`invalid:harness`, `not_countable:invalid`**. Preserved in full as historical evidence.
- **Replacement attempt** `run_xmlttozhohhtrlg6yfallqlvqa` (ordinal 2) — a distinct attempt,
  linked via `original_attempt_id`/`predecessor_attempt_id` both pointing at the original. Its
  real cleanup executed and verified fully clear. Effective status: **`valid`, `countable`**.

Cell 1's one main countable observation for this pilot is the **replacement's** result. The
original is never discarded or merged into it — it stands as a separate, permanently
non-countable historical record, exactly as the series' append-only design requires.

No second replacement was approved or attempted (`max_replacements_per_cell: 1`, fully used); no
E3 contingency attempt exists anywhere in the event log.

### 3.2 Pilot accounting

| Quantity | Count |
|---|---|
| Planned cells | 6 |
| Original attempts | 6 |
| Replacement attempts | 1 |
| Total execution attempts | 7 |
| Countable main observations | 6 |
| Historical non-countable attempts | 1 |
| E3 attempts | 0 |

The six countable main observations already **include** the Cell 1 replacement
(`run_xmlttozhohhtrlg6yfallqlvqa`) as Cell 1's observation; it is not counted in addition to six.
6 original attempts + 1 replacement = 7 execution attempts; 7 − 1 historical non-countable original
(`run_chl55f5gx6o7naprqdj33i24ou`) = 6 countable observations, one per planned cell.

## 4. Infrastructure findings discovered by the pilot

Running real attempts against the frozen spec and schedule surfaced two concrete production defects in the
series driver itself (not in the pilot tasks or treatments). Both were fixed and the fixes
validated by subsequent real attempts within this same pilot.

### 4.1 Production cleanup silently used dry-run cleanup

`series run-next --execute` never passed an explicit cleanup runner into the execution path, so it
silently fell back to the offline no-op `DryCleanupRunner` in real production runs — exactly the
condition that produced Cell 1's original attempt's `invalid:harness` status. Fixed by always
constructing a real, scope-guarded cleanup runner for the production path, adding a post-cleanup
residue verification step, and failing an attempt closed (`invalid:harness`) if a real cleanup
did not fully succeed. Validated: every subsequent real attempt in this pilot (6 of 7) shows
`cleanup.performed: true` and fully clear residue.

### 4.2 A recoverable halt had no auditable way back to execution

The series-wide halt flag treated any historical halt event as permanent, with no route back to
execution even for an operator-reviewed, fully remediated incident — making the already-frozen
replacement policy unusable after exactly this kind of recoverable infrastructure incident. Fixed
by structurally distinguishing hard safety halts (leak, carryover, C2 phase-1 write — which remain
permanently non-resumable) from a recoverable cleanup-remediation halt, and adding one new,
explicit, append-only `series_resumed` event that only succeeds after re-verifying the remediation
evidence itself (not merely trusting a label). The original `series_halted` event is never edited
or removed. Validated: this pilot's own recovery (remediate → resume → approve → execute the
replacement) is the event sequence recorded in §3.1.

### 4.3 Methodology note: harness evolution during the pilot

- The task packages, treatments, frozen spec (`spec_hash`) and deterministic schedule
  (`schedule_hash`) remained frozen throughout the pilot.
- The harness implementation itself did **not**: the first real attempt exposed the production
  cleanup-wiring defect (§4.1), followed by the recoverable-halt/resume defect (§4.2), and both
  were fixed in the harness source mid-pilot.
- The historical Cell 1 original predates the cleanup fix and remains non-countable; the
  subsequent countable pilot observations exercised the corrected production path.
- No exact per-attempt harness source commit/hash was recorded, and none is claimed here.

Therefore this pilot validates the machinery and protocol, but it is **not** a comparative
experiment run under one immutable harness source snapshot. The harness implementation must be
frozen before the final 54-run benchmark begins.

## 5. C2 protocol evidence

Both main C2 pilot observations (Cell 3, P-TS-01; Cell 4, P-PY-01) independently demonstrated:

- phase 1 was genuinely read-only (working-copy snapshot unchanged except `__pycache__`, no extra
  Claude project state, no user-level instructions — `phase1_readonly.ok: true` both runs);
- no phase-1 write protocol violation (`c2_protocol: "ok"` both runs);
- same-session continuation — phase 2 resumed the exact session phase 1 used, never a new one
  (`session_continuity_verified: true`, `session_ok: true` on both phases, both runs);
- the fixed approval message was used verbatim to start phase 2, never conditioned on the phase-1
  plan;
- requested and observed model matched (`claude-sonnet-5`) independently on every phase of every
  run;
- the shared 900-second total deadline was honored — phase 2 received the genuine remainder, never
  a reset (§2).

**Therefore: E3 contingency trigger = false.** Both main C2 runs reached and completed phase 2
successfully; the pre-declared contingency for a C2 phase-2 failure was never needed.

## 6. Pilot interpretation boundary

This pilot validates the benchmark **machinery and protocol** — deterministic scheduling,
treatment isolation, the C2 two-phase contract, model provenance, cleanup/residue integrity, and
the replacement/recovery policy all executed as designed against two real tasks.

**It is not evidence that C0, C1, or C2 is generally superior.** Two tasks, one repetition each,
is not a statistically meaningful comparison, and no such comparison is drawn here. Task success
rates observed in this pilot must not be cited as a final benchmark conclusion, used to rank
configurations, or referenced as a result in any report about C0/C1/C2 effectiveness.

## 7. Closeout status

PILOT-V1 COMPLETE — READY FOR FINAL TASKSET AUTHORING
