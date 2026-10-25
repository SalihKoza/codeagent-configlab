"""Study-01 freeze snapshot: build and verify ``snapshot.json`` (Gate 6, freeze/provenance only).

This utility never changes harness behavior. It imports the validated harness read-only
(``hashing``, ``series``, ``task_package``) and writes no files: ``build`` prints the snapshot JSON to
stdout; ``verify`` and ``rehash`` only read.

Hash rule (``STUDY_01_PROTOCOL.md`` §7.1/§7.2, no self-reference)::

    study_snapshot_hash = hashing.canonical_json_hash(snapshot["payload"])

``snapshot["payload"]`` holds every frozen Study-01 input. ``study_snapshot_hash`` and
``provenance`` (runtime / path-bound evidence) sit beside the payload, never inside it, and the
later ``study_freeze_commit`` is recorded only outside the committed content.

Usage (from WSL, repository root)::

    python3 -B studies/study01/snapshot_tool.py build  [--evidence-store DIR] > studies/study01/snapshot.json
    python3 -B studies/study01/snapshot_tool.py verify [--evidence-store DIR]
    python3 -B studies/study01/snapshot_tool.py rehash --snapshot PATH
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import re
import stat
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from codeagent_configlab import series as S  # noqa: E402
from codeagent_configlab.evaluator_sandbox import EVALUATOR_SANDBOX_VERSION, PYTHON_BINARY  # noqa: E402
from codeagent_configlab.hashing import canonical_json_hash, sha256_file  # noqa: E402
from codeagent_configlab.task_package import TaskPackage  # noqa: E402

SNAPSHOT_SCHEMA = "configlab-study-snapshot/v1"
HARNESS_GIT_SHA = "c9e2e32c030d129e9cef53dca5c7e3b539c675f6"   # Gate-5 S7
OPERATIONAL_SERIES_ROOT = "/home/cclab/cclab-study01/series/study01-v1"   # provenance only
HASH_RULE = ("study_snapshot_hash = codeagent_configlab.hashing.canonical_json_hash(payload) = "
             "sha256 of json.dumps(payload, sort_keys=True, separators=(',', ':'), "
             "ensure_ascii=False) encoded UTF-8; payload excludes study_snapshot_hash, provenance "
             "and study_freeze_commit")

# Gate-4 PASS evidence (Gate-5 S1), relative to the gate results store.
GATE_EVIDENCE = {
    "F-PY-BUG-01": ("20261013T171817Z", "7f3a71c764d08f603442f51739cfad6548a12b922ea98f291145feb7c670e4fb"),
    "F-PY-FEAT-01": ("20261013T175813Z", "50923f60453cba4371c202abab282f635197166090b71460d89c72ea97f95857"),
    "F-PY-REF-01": ("20261013T182555Z", "8e7aa560955eadf0faef051495ac86f718aa5337bfd7527e41a844c85295a6dd"),
    "F-TS-BUG-01": ("20261023T154247Z", "04c74688eb733789fc8ae0ff76364b99110bfc856beb912f83189a53b07a743c"),
    "F-TS-FEAT-01": ("20261023T161302Z", "26f4420dd453b86dd0718c8181e0df8ee82eee4724808e459e2374d5dba0b928"),
    "F-TS-REF-01": ("20261023T171829Z", "5d34264970ff36c8ae16a54844896991c3647386b02e96483b9e82559eff5af7"),
}
# Gate-environment evaluator-sandbox policy hashes: path-bound, provenance only (Gate-5 S8).
GATE_ENV_POLICY_HASH = {
    "F-PY-BUG-01": "dfff2f1ce0cbbd591ca593563a7037cfad00508860089222a72daa722fad0a43",
    "F-PY-FEAT-01": "62061d1a2a70dca091ddd8af5ec51158ee99dbfae9b3623f4356b569cdc1de10",
    "F-PY-REF-01": "ed4b7a43570d37ef2731d9c8d7d5817fb697df4a90de1145e1de6d42874a3db4",
    "F-TS-BUG-01": "bc25738fcf59b8f3845f24579dd98220ac41d4a4f2686a7ffdf3783862418d89",
    "F-TS-FEAT-01": "bac19cbdae576176ffa1e573072759988e83c70f139792c59479bd945bfff7c7",
    "F-TS-REF-01": "a897d3cd3362713ad13ac718f31fa4445da6a9d81917c73ea10becdac58c6718",
}
SOURCE_SCOPE = {   # Gate-5 S2
    "F-PY-BUG-01": ["msgheaders/**"], "F-PY-FEAT-01": ["eventlog/**"],
    "F-PY-REF-01": ["svcconfig/**"], "F-TS-BUG-01": ["src/**"], "F-TS-FEAT-01": ["src/**"],
    "F-TS-REF-01": ["src/**"],
}
SCOPE_EXCLUDED = {
    "python": ["tests/**", "_hidden_tests/**", "README.md", "CLAUDE.md", ".claude/**",
               "**/__pycache__/**", ".pytest_cache/**", "every path outside the scope directory"],
    "typescript": ["test/**", "_hidden_tests/**", "dist/**", "*.tsbuildinfo", "node_modules/**",
                   "package.json", "package-lock.json", "tsconfig.json", "README.md", "CLAUDE.md",
                   ".claude/**", "every path outside src/"],
}
TREATMENT_FILES = {"claude_md": "treatments/pilot-v1/claude_md.md",
                   "planning_wrapper": "treatments/pilot-v1/planning_wrapper.txt",
                   "approval_message": "treatments/pilot-v1/approval_message.txt"}
PROTOCOL_ROLES = {
    "study_protocol": "docs/STUDY_01_PROTOCOL.md",
    "experiment_protocol": "docs/EXPERIMENT_PROTOCOL_V0.md",
    "gate5_decisions": "docs/STUDY_01_GATE5_DECISIONS.md",
    "gate3_recheck": "docs/STUDY_01_GATE3_RECHECK.md",
    "task_standard": "docs/PILOT_TASK_STANDARD.md",
    "run_manifest": "docs/RUN_MANIFEST_V0.md",
    "series_contract": "docs/PILOT_SERIES_V0.md",
    "pilot_plan": "docs/PILOT_PLAN.md",
}
SERIES_FILES = ("series.json", "spec.json", "schedule.json")
# Payload must hold no result/attempt/model-output material and no user-specific absolute path.
FORBIDDEN_PAYLOAD_KEYS = {"study_snapshot_hash", "study_freeze_commit", "provenance", "run_id",
                          "attempt_id", "workspace_token", "observed_model", "agent_outcome",
                          "acceptance", "regression", "result", "events", "built_at"}
FORBIDDEN_VALUE_PATTERNS = (r"/home/", r"/mnt/", r"[A-Za-z]:\\", r"\brun_[a-z0-9]{26}\b",
                            r"\bwt_[a-z0-9]{10,}\b")


def _rel(p: Path) -> str:
    return p.resolve().relative_to(REPO).as_posix()


def _file_id(rel: str) -> dict:
    p = REPO / rel
    return {"path": rel, "sha256": sha256_file(p), "bytes": p.stat().st_size}


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _toolchain(pkg: TaskPackage) -> dict:
    if pkg.language == "python":
        return {"python_binary": PYTHON_BINARY, "dependencies": "stdlib only"}
    lock = pkg.pristine / "package-lock.json"
    ts_pkg = _load_json(pkg.pristine / "node_modules" / "typescript" / "package.json")
    return {"node": S.NODE_VERSION, "typescript": ts_pkg["version"],
            "package_lock_sha256": sha256_file(lock)}


def _structural_sha(pkg: TaskPackage):
    for name in ("structure_check.py", "structure_check.cjs"):
        f = pkg.hidden / name if pkg.hidden else None
        if f is not None and f.is_file():
            return {"path": f"hidden/{name}", "sha256": sha256_file(f)}
    return None


def build_payload() -> dict:
    config = S.SeriesConfig.from_json(HERE / "series.json")
    spec = _load_json(HERE / "spec.json")
    sched = _load_json(HERE / "schedule.json")
    spec_by_task = {t["task_id"]: t for t in spec["tasks"]}

    tasks = []
    for pkg in sorted(config.packages(), key=lambda p: p.task_id):
        ts, ev_sha = GATE_EVIDENCE[pkg.task_id]
        tasks.append({
            "task_id": pkg.task_id, "language": pkg.language, "task_category": pkg.task_category,
            "package_dir": _rel(pkg.root),
            "task_version_hash": pkg.version_hash(), "statement_hash": pkg.statement_hash,
            "evaluator_identity": pkg.evaluator_identity(),
            "structural_check": _structural_sha(pkg),
            "generated_outputs": list(pkg.generated_outputs),
            "source_scope": SOURCE_SCOPE[pkg.task_id],
            "toolchain": _toolchain(pkg),
            "gate": {"status": spec_by_task[pkg.task_id]["gate_status"],
                     "evidence_file": f"{pkg.task_id}/{ts}.json", "generated_at": ts,
                     "evidence_sha256": ev_sha},
        })

    docs = sorted((REPO / "docs").glob("*.md"))
    payload = {
        "schema": SNAPSHOT_SCHEMA,
        "study_id": "study01",
        "hash_rule": HASH_RULE,
        "protocol": {
            "documents": {_rel(d): sha256_file(d) for d in docs},
            "roles": {role: _file_id(rel) for role, rel in sorted(PROTOCOL_ROLES.items())},
            "amendments_in_force": [
                {"id": "A1", "document": "docs/EXPERIMENT_PROTOCOL_V0.md", "section": "§13",
                 "title": "V0 credential-isolation execution boundary", "dated": "2026-09-25"},
                {"id": "A2", "document": "docs/EXPERIMENT_PROTOCOL_V0.md", "section": "§12a",
                 "title": "neutral baseline and treatment state", "dated": "2026-09-27"},
            ],
        },
        "harness": {
            "harness_git_sha": HARNESS_GIT_SHA,
            "evaluator_sandbox_version": EVALUATOR_SANDBOX_VERSION,
            "toolchain": spec["toolchain"],
            "envelope": spec["envelope"],
        },
        "evaluator_identity_rule": (
            "Gate-5 S8: a task's binding evaluator identity is its evaluator_identity + evaluator "
            "sandbox semantic version g5s-v2 + harness_git_sha. Runtime sandbox policy_hash values "
            "contain absolute paths and are provenance only, never a snapshot key."),
        "treatments": {
            "policy": ("Gate-5 S3: exact byte-for-byte reuse of pilot-v1; one common CLAUDE.md for "
                       "all six tasks and both languages; no treatment tuning"),
            "freeze_record": _file_id("treatments/pilot-v1/FREEZE.json"),
            **{role: _file_id(rel) for role, rel in TREATMENT_FILES.items()},
            "spec_treatment_hashes": spec["treatment"],
        },
        "execution": {
            "model_request": spec["model_request"],
            "model_rule": ("requested model identity; the observed model is checked per invocation "
                           "and a mismatch fails closed (invalid:harness); no silent fallback"),
            "effort_request": spec["effort_request"],
            "timeout_seconds": spec["timeout_seconds"],
            "c2_deadline": ("one shared deadline across C2 phase 1 + phase 2; phase 2 receives the "
                            "remainder, never a fresh 900 s; the inter-phase gap is not charged"),
        },
        "tasks": tasks,
        "analysis": {
            "source_scope_rule": {
                "membership": "a path counts only if it matches the task's source scope and is not excluded",
                "excluded": SCOPE_EXCLUDED,
                "rule_1_renames": ("a rename counts as a changed source file when either the old or "
                                   "the new path is inside the scope"),
                "rule_2_unavailable_line_delta": (
                    "if the textual line delta is unavailable (whole final.diff withheld, or an entry "
                    "marked 'binary or oversized file; not inlined' / 'start content unavailable; not "
                    "inlined'), an in-scope file still counts as changed and its line delta is "
                    "recorded as unknown/withheld, never 0; withheld changed_files path names make "
                    "scope membership unknown"),
                "rule_3": "changed-file count and diff size are descriptive only, never a quality metric",
            },
            "token_usage": ("S10: EXCLUDED FROM FORMAL STUDY-01 METRICS; raw usage fields/events are "
                            "preserved when present; missing usage is never 0; total_cost_usd is not "
                            "a billed cost under Claude Pro"),
            "unnecessary_change_rubric": ("S11: EXCLUDED FROM FORMAL STUDY-01 METRICS; no frozen "
                                          "rubric exists; no weighted or composite quality score"),
            "replacement_policy": {
                "rule": ("C-a: pilot-validated policy unchanged (series.replacement_decision): "
                         "countable -> complete, no replacement; evaluation_pending -> evaluator "
                         "re-evaluation on the preserved final working copy, never an agent rerun; "
                         "external interruption / invalid:infrastructure / invalid:harness / "
                         "preflight_failed -> operator-approved replacement only; invalid:fixture -> "
                         "replacement only with an operator note; invalid:leak / invalid:carryover / "
                         "invalid:c2_protocol+phase1_write -> series halt (hard stop); real cleanup "
                         "failure -> recoverable halt; anything else -> no_valid_attempt; at most "
                         "one replacement per cell; no outcome-quality reruns; every attempt "
                         "preserved; replacements never increase planned N"),
                "ordering": ("approved replacement attempts run only after all 54 planned original "
                             "cells have been attempted, in schedule order (Series._next), never at "
                             "the end of the current block"),
                "spec_replacement_policy": spec["replacement_policy"],
            },
            "agent_time_binding": {
                "c0_c1": "process.json -> elapsed_seconds",
                "c2_phase1": "c2.json -> phases[label == 'phase1'].process.elapsed_seconds",
                "c2_phase2": ("c2.json -> phases[label == 'phase2'].process.elapsed_seconds; not "
                              "started (c2.json.invocations == 1) is reported as not started, never 0"),
                "c2_total": "phase1 + phase2 agent elapsed (phase 1 only if phase 2 did not start)",
                "excluded": ("c2.json.inter_phase_gap_seconds; evaluator, cleanup and lifecycle time; "
                             "result.json.duration_seconds and c2.json.phases[].duration_seconds are "
                             "not the performance metric"),
                "timeout": ("result.json agent_outcome == 'timeout' with run_validity == 'valid'; "
                            "process timed_out true, termination 'timeout_terminated', "
                            "deadline_budget_seconds; a missing process record is missing, never 0"),
            },
            "results_presentation": {
                "rule": "C-c: STUDY_01_PROTOCOL.md §8 adopted unchanged",
                "key_rules": [
                    "task-by-task results first",
                    "planned-cell denominator: R resolved · F failed · M no countable observation / N planned",
                    "separate attempt / replacement / non-countable accounting",
                    "18 planned cells per configuration, 54 overall",
                    "primary contrasts RQ1 = C1 - C0 and RQ2 = C2 - C1; C2 - C0 descriptive only",
                    "agent time over all countable attempts with success/failure/timeout visible",
                    "C2 phase 1 + phase 2 breakdown and total",
                    "source-scoped changed files and diff size descriptive only",
                    "no weighted composite score",
                    "no significance or generalization claim unsupported by the six-task design",
                ],
            },
        },
        "run_order": {
            "series_id": spec["pilot_version"],
            "namespace": spec["namespace"],
            "configurations": spec["configurations"],
            "repetitions": spec["repetitions"],
            "planned_cells": len(sched["cells"]),
            "order_seed_text": spec["order_seed_text"],
            "no_same_task_consecutively": False,
            "order_rule": sched["order_rule"],
            "block_seeds": sched["block_seeds"],
            "spec_hash": spec["spec_hash"],
            "schedule_hash": sched["schedule_hash"],
            "files": {name: _file_id(_rel(HERE / name)) for name in SERIES_FILES},
            "cells": [{k: c[k] for k in ("position", "cell_id", "task_id", "configuration", "repetition")}
                      for c in sched["cells"]],
        },
    }
    return payload


def provenance() -> dict:
    return {
        "classification": "runtime / path-bound evidence; not covered by study_snapshot_hash",
        "operational_series_root": OPERATIONAL_SERIES_ROOT,
        "gate_evidence_store": "/home/cclab/cclab-final-gate/results/gate",
        "gate_env_sandbox_policy_hash": GATE_ENV_POLICY_HASH,
        "python_version": platform.python_version(),
        "built_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ----------------------------------------------------------------------------------- checks --

def check_series(errors: list) -> None:
    config = S.SeriesConfig.from_json(HERE / "series.json")
    spec = _load_json(HERE / "spec.json")
    sched = _load_json(HERE / "schedule.json")
    if S.build_spec(config) != spec:
        errors.append("spec.json differs from build_spec(series.json)")
    if S.generate_schedule(spec) != sched:
        errors.append("schedule.json differs from generate_schedule(spec.json)")
    if S._validate(spec, "pilot-series-spec.schema.json"):
        errors.append("spec.json fails the series spec schema")
    if S.readiness_errors(spec):
        errors.append(f"spec readiness errors: {S.readiness_errors(spec)}")
    cells = sched["cells"]
    tasks = {t["task_id"]: t["task_version_hash"] for t in spec["tasks"]}
    if spec["namespace"] != S.NAMESPACE_FINAL:
        errors.append("namespace is not FINAL")
    if len(cells) != 54 or [c["position"] for c in cells] != list(range(1, 55)):
        errors.append("schedule does not have positions 1..54")
    if len(tasks) != 6 or any(t.startswith("P-") for t in tasks):
        errors.append("task set is not six FINAL tasks")
    if set(Counter(c["task_id"] for c in cells).values()) != {9}:
        errors.append("each task must appear 9 times")
    if Counter(c["configuration"] for c in cells) != {"C0": 18, "C1": 18, "C2": 18}:
        errors.append("each configuration must appear 18 times")
    pairs = {}
    for c in cells:
        pairs.setdefault((c["task_id"], c["configuration"]), []).append(c["repetition"])
    if len(pairs) != 18 or any(sorted(r) != [1, 2, 3] for r in pairs.values()):
        errors.append("each task x configuration needs repetitions 1, 2, 3 exactly once")
    if len({c["cell_id"] for c in cells}) != 54:
        errors.append("cell_ids are not unique")
    if any(c["task_version_hash"] != tasks[c["task_id"]] for c in cells):
        errors.append("a cell does not point to the frozen task version")
    if any(c["cell_id"] != S.cell_id_for(spec, {"task_id": c["task_id"],
                                                 "task_version_hash": c["task_version_hash"]},
                                          c["configuration"], c["repetition"]) for c in cells):
        errors.append("a cell_id does not recompute")


def check_payload_content(payload: dict, errors: list) -> None:
    def walk(obj, where):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in FORBIDDEN_PAYLOAD_KEYS:
                    errors.append(f"payload has forbidden key {where}.{k}")
                walk(v, f"{where}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{where}[{i}]")
        elif isinstance(obj, str):
            for pat in FORBIDDEN_VALUE_PATTERNS:
                if re.search(pat, obj):
                    errors.append(f"payload value at {where} matches {pat!r}")
    walk(payload, "payload")


def check_evidence(store: Path, errors: list) -> None:
    for tid, (ts, sha) in GATE_EVIDENCE.items():
        p = store / tid / f"{ts}.json"
        if sha256_file(p) != sha:
            errors.append(f"{tid}: gate evidence sha256 differs")
        elif _load_json(p).get("status") != "PASS":
            errors.append(f"{tid}: gate evidence is not PASS")


def check_tasks(payload: dict, errors: list) -> None:
    spec = _load_json(HERE / "spec.json")
    spec_by_task = {t["task_id"]: t for t in spec["tasks"]}
    for t in payload["tasks"]:
        pkg = TaskPackage.load(REPO / t["package_dir"])
        if pkg.gate_errors():
            errors.append(f"{t['task_id']}: gate_errors {pkg.gate_errors()}")
        s = spec_by_task[t["task_id"]]
        for key in ("task_version_hash", "statement_hash", "evaluator_identity"):
            if s[key] != t[key]:
                errors.append(f"{t['task_id']}: {key} differs from spec.json")


def rehash(snapshot_path: Path) -> int:
    snap = _load_json(snapshot_path)
    h = canonical_json_hash(snap["payload"])
    ok = h == snap["study_snapshot_hash"]
    # Fail closed: every referenced series file must exist as a regular file with its recorded hash.
    statuses = {}
    for name, f in snap["payload"]["run_order"]["files"].items():
        p = snapshot_path.parent / name
        if not os.path.lexists(p):
            statuses[name] = "missing"
        elif not stat.S_ISREG(p.lstat().st_mode):
            statuses[name] = "not_a_regular_file"
        elif sha256_file(p) != f["sha256"]:
            statuses[name] = "mismatch"
        else:
            statuses[name] = "match"
    files_ok = bool(statuses) and all(s == "match" for s in statuses.values())
    print(json.dumps({"recomputed": h, "recorded": snap["study_snapshot_hash"],
                      "hash_match": ok, "series_files": statuses,
                      "series_file_hashes_match": files_ok}, indent=2))
    return 0 if ok and files_ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["build", "verify", "rehash"])
    ap.add_argument("--evidence-store", type=Path, default=None)
    ap.add_argument("--snapshot", type=Path, default=HERE / "snapshot.json")
    args = ap.parse_args(argv)

    if args.action == "rehash":
        return rehash(args.snapshot)

    errors: list = []
    check_series(errors)
    payload = build_payload()
    check_tasks(payload, errors)
    check_payload_content(payload, errors)
    if args.evidence_store is not None:
        check_evidence(args.evidence_store, errors)

    if args.action == "build":
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        snap = {"payload": payload, "study_snapshot_hash": canonical_json_hash(payload),
                "provenance": provenance()}
        sys.stdout.write(json.dumps(snap, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        return 0

    snap = _load_json(args.snapshot)
    if snap["payload"] != payload:
        diff = sorted(k for k in set(payload) | set(snap["payload"])
                      if payload.get(k) != snap["payload"].get(k))
        errors.append(f"recorded payload differs from recomputed payload in {diff}")
    h = canonical_json_hash(snap["payload"])
    if h != snap["study_snapshot_hash"]:
        errors.append("study_snapshot_hash does not match the recorded payload")
    print(json.dumps({"study_snapshot_hash": h, "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
