# Study 01 — Freeze Material (Gate 6)

This directory is the Study-01 freeze material required by `docs/STUDY_01_PROTOCOL.md` §7. It
binds the Gate-5 operator decisions (`docs/STUDY_01_GATE5_DECISIONS.md`) and the generated FINAL
run order into one deterministic identity, `study_snapshot_hash`. It holds no results.

| File | Role |
|---|---|
| `series.json` | Operator series config for the existing `series` driver (`pilot_version` `study01-v1`, namespace `FINAL`). Paths are relative to this directory |
| `spec.json` | Byte copy of the operational `spec.json` written by `series freeze` |
| `schedule.json` | Byte copy of the operational `schedule.json` written by the same, single `series freeze`. This is the frozen 54-cell order |
| `snapshot.json` | `{"payload", "study_snapshot_hash", "provenance"}` |
| `snapshot_tool.py` | Freeze/provenance-only utility. It builds and verifies `snapshot.json`, imports the harness read-only and writes no files |

## Identities

| Identity | Value |
|---|---|
| `harness_git_sha` (Gate-5 S7) | `c9e2e32c030d129e9cef53dca5c7e3b539c675f6` |
| Series | `study01-v1`, namespace `FINAL`, 6 tasks × C0/C1/C2 × 3 repetitions = 54 planned cells |
| `spec_hash` | `84d61cb647fb226555c8b24a5b1334cccfdb485bd6dd7901127493b34bcf7674` |
| `schedule_hash` | `51700202b74950a88813b494530b9efdbdcaced2d0524e0186752f7db1241664` |
| `study_snapshot_hash` | `3ad54204775e12f55e14c149b2e9bc6e8e9d6194529e47e97f5fc2ae44f32d01` |

`harness_git_sha` is **not** the commit that adds this directory. The freeze commit
(`study_freeze_commit`) is recorded only outside the content it identifies (protocol §7.1).

## Hash rule

`study_snapshot_hash = codeagent_configlab.hashing.canonical_json_hash(snapshot["payload"])`

This is the SHA-256 of `json.dumps(payload, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)`, encoded as UTF-8.

The payload holds every frozen input:
- the protocol documents with their amendments A1 and A2;
- the harness identity;
- the treatment identities;
- the requested model, effort and timeout;
- the six task and evaluator identities;
- the analysis decisions (S2, S10, S11, C-a, C-b, C-c);
- the seed, spec, schedule and all 54 cells.

The payload never contains `study_snapshot_hash`, `study_freeze_commit`, timestamps, absolute user
paths or any result.

`provenance` is runtime / path-bound evidence and is not hashed. It holds:
- the operational series root;
- the gate-evidence store path;
- the gate-environment sandbox `policy_hash` values;
- the Python version;
- the build time.

## Operational series root

The executing series lives outside Git, at `/home/cclab/cclab-study01/series/study01-v1/`. Its
`spec.json` and `schedule.json` are byte-identical to the copies here. Execution uses:

```
python -m codeagent_configlab series <action> --config studies/study01/series.json --harness-root /home/cclab/cclab-study01
```

## Verify

From WSL, at the repository root:

```
python3 -B studies/study01/snapshot_tool.py verify [--evidence-store /home/cclab/cclab-final-gate/results/gate]
python3 -B studies/study01/snapshot_tool.py rehash --snapshot studies/study01/snapshot.json
```

`verify` recomputes the following and requires each to match:
- the whole payload, from the repository;
- the spec, via `build_spec(series.json)`;
- the schedule, via `generate_schedule(spec)`;
- the 54-cell invariants;
- the task identities and `gate_errors()`;
- the snapshot hash.
