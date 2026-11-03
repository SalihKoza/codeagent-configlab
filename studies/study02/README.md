# Study 02 — Freeze Material (Gate 7I)

This directory is the Study-02 freeze material. It binds the frozen protocol, analysis plan,
execution policy, treatment assignment, and the generated FINAL run order into one deterministic
identity, `study_snapshot_hash`. It holds no results — no Study-02 production candidate execution
has occurred.

**Convention note**: Study-01's equivalent freeze material (`studies/study01/`) keeps its
protocol/analysis-plan/execution-policy prose under top-level `docs/`, referencing those files by
path+sha256 from its snapshot payload. This directory instead consolidates Study-02's prose
documents directly alongside the data artifacts — a deliberate choice for this study's freeze
package (one audit-ready directory, given Study-02's broader multi-gate design history), not an
oversight of Study-01's convention. The hash-rule mechanism itself, and the path+sha256
reference pattern used to bind those documents into the payload, are otherwise identical to
Study-01's.

| File | Role |
|---|---|
| `STUDY_02_PROTOCOL.md` | Frozen protocol: research question, design, primary/validity/eligibility structure, replacement policy, timing, Study-03 firewall |
| `STUDY_02_ANALYSIS_PLAN.md` | Frozen analysis plan: outcome table, exclusions, validity/eligibility/outcome-success separation |
| `STUDY_02_EXECUTION_POLICY.md` | Frozen execution policy: timing budget, external-invalidity taxonomy, replacement policy, model/effort/harness identity |
| `STUDY_02_TREATMENT_MAPPING.csv` | The 12-row `task_id -> family CLAUDE.md` assignment, human-readable |
| `STUDY_02_ENVIRONMENT.json` | Live-verified environment/toolchain provenance at freeze |
| `STUDY_02_FREEZE.json` | Descriptive freeze-status summary (status, key identities, production-attempt count) — `snapshot.json` is the authoritative hash-bearing artifact, this file is a convenience pointer to it |
| `series.json` | Operator series config for the existing `series` driver (`pilot_version` `study02-v1`, namespace `FINAL`). Paths are relative to this directory |
| `spec.json` | Byte copy of the operational `spec.json` written by `series freeze` |
| `schedule.json` | Byte copy of the operational `schedule.json` written by the same, single `series freeze`. This is the frozen 48-cell order |
| `snapshot.json` | `{"payload", "study_snapshot_hash", "provenance"}` — the authoritative frozen artifact |
| `snapshot_tool.py` | Freeze/provenance-only utility. It builds and verifies `snapshot.json`, imports the harness read-only and writes no files |

## Identities

| Identity | Value |
|---|---|
| `harness_git_sha` | `1f576bf245411b00cd7856ac835bd651fcd281d8` |
| `study02_implementation_git_sha` | `bbf8bba2ee7ffdefaca392f5c50a7d4ae585590e` |
| Series | `study02-v1`, namespace `FINAL`, 12 tasks × C1/C2 × 2 repetitions = 48 planned cells |
| `spec_hash` | `175c882abc42ccdd7b5ed488cdcac789130fdb09a93a2f7199d1863d5e084682` |
| `schedule_hash` | `6a1f256f5fbb4502a50cbb20b6db61751144e263f45bb51294953056555c86d5` |
| `canonical_task_treatment_mapping_hash` | `61fa81d034bf5a65d9f88e524cb15355ec4da6249ae386886666f08e69b2ca0a` |
| `order_projection_hash` (external diagnostic, randomization/order identity) | `bb8df6cfb8e23c120306f1158e7d8423f319e2ee4cfd8e0d74cbac7633c7c7bb` |
| `study_snapshot_hash` | `3d7f238963577fb3f99ea675e6e70c2a0611ac29d5c7d36af4a9deface5a0a37` |

`harness_git_sha` is **not** the commit that adds this directory. The freeze commit
(`study_freeze_commit`) is recorded only outside the content it identifies, exactly as in
Study-01's convention.

Historical identities, unchanged by this freeze: Study-01 harness SHA
`c9e2e32c030d129e9cef53dca5c7e3b539c675f6`; two-arm support commit
`d263dc32904c171c5da74e8ed1cf084c7a705bfa`.

## Hash rule

`study_snapshot_hash = codeagent_configlab.hashing.canonical_json_hash(snapshot["payload"])`

This is the SHA-256 of `json.dumps(payload, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)`, encoded as UTF-8 — identical mechanism to Study-01's.

The payload holds every frozen input:
- the protocol/analysis-plan/execution-policy documents (path + sha256);
- the harness and Study-02 implementation identities;
- the treatment identities (six family files, shared wrapper, shared approval message) and the
  canonical, task-sorted task→treatment assignment;
- the requested model, effort and timeout;
- the twelve task and evaluator identities;
- the analysis decisions (research question, endpoints, replacement policy);
- the seed, spec, schedule and all 48 cells.

The payload never contains `study_snapshot_hash`, `study_freeze_commit`, timestamps, absolute
user paths or any result.

`provenance` is runtime / path-bound evidence and is not hashed. It holds the planned (not yet
created) operational series root, the Python version, and the build time.

## Operational series root (not yet created)

No Study-02 production series has been created. Once a separate, operator-controlled execution
gate begins production, the executing series is expected to live outside Git at
`/home/cclab/cclab-study02/series/study02-v1/`, with its `spec.json`/`schedule.json` byte-identical
to the copies here, executed via:

```
python -m codeagent_configlab series <action> --config studies/study02/series.json --harness-root /home/cclab/cclab-study02
```

## Verify

From WSL, at the repository root:

```
python3 -B studies/study02/snapshot_tool.py verify
python3 -B studies/study02/snapshot_tool.py rehash --snapshot studies/study02/snapshot.json
```

`verify` recomputes the following and requires each to match:
- the whole payload, from the repository;
- the spec, via `build_spec(series.json)`;
- the schedule, via `generate_schedule(spec)`;
- the 48-cell invariants (12 tasks × 2 configurations × 2 repetitions, no C0, no C3, 24/24 split,
  each task×configuration pair exactly once per repetition, unique cell IDs, recomputable cell
  IDs);
- the task identities and `gate_errors()`;
- the frozen task→treatment routing (12 entries, 6 distinct family hashes);
- the snapshot hash.
