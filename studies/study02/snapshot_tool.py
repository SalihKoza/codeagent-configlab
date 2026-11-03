"""Study-02 freeze snapshot: build and verify ``snapshot.json`` (Gate 7I, freeze/provenance only).

This utility never changes harness behavior. It imports the validated harness read-only
(``hashing``, ``series``, ``task_package``) and writes no files: ``build`` prints the snapshot JSON
to stdout; ``verify`` and ``rehash`` only read.

Hash rule (same convention as ``studies/study01/snapshot_tool.py``, no self-reference)::

    study_snapshot_hash = hashing.canonical_json_hash(snapshot["payload"])

``snapshot["payload"]`` holds every frozen Study-02 input. ``study_snapshot_hash`` and
``provenance`` (runtime / path-bound evidence) sit beside the payload, never inside it, and the
later ``study_freeze_commit`` is recorded only outside the committed content.

Usage (from WSL, repository root)::

    python3 -B studies/study02/snapshot_tool.py build  > studies/study02/snapshot.json
    python3 -B studies/study02/snapshot_tool.py verify
    python3 -B studies/study02/snapshot_tool.py rehash --snapshot PATH
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
from codeagent_configlab.hashing import canonical_json_hash, sha256_file  # noqa: E402
from codeagent_configlab.task_package import TaskPackage  # noqa: E402

SNAPSHOT_SCHEMA = "configlab-study-snapshot/v1"
HARNESS_GIT_SHA = "1f576bf245411b00cd7856ac835bd651fcd281d8"
STUDY02_IMPLEMENTATION_GIT_SHA = "bbf8bba2ee7ffdefaca392f5c50a7d4ae585590e"
PLANNED_OPERATIONAL_SERIES_ROOT = "/home/cclab/cclab-study02/series/study02-v1"   # provenance only; not yet created
HASH_RULE = ("study_snapshot_hash = codeagent_configlab.hashing.canonical_json_hash(payload) = "
             "sha256 of json.dumps(payload, sort_keys=True, separators=(',', ':'), "
             "ensure_ascii=False) encoded UTF-8; payload excludes study_snapshot_hash, provenance "
             "and study_freeze_commit")

FAMILY_OF = {
    "S2-PY-BUG-01": "throttlekit", "S2-PY-REF-02": "throttlekit",
    "S2-PY-BUG-02": "stocktrack", "S2-PY-FEAT-01": "stocktrack",
    "S2-PY-FEAT-02": "configmerge", "S2-PY-REF-01": "configmerge",
    "S2-TS-BUG-01": "dedupe-cache", "S2-TS-REF-02": "dedupe-cache",
    "S2-TS-BUG-02": "qs-normalize", "S2-TS-FEAT-01": "qs-normalize",
    "S2-TS-FEAT-02": "mini-queue", "S2-TS-REF-01": "mini-queue",
}
# Prose documents live inside this same freeze directory (a deliberate consolidation choice for
# Study-02, documented in README.md -- Study-01 instead kept its protocol prose under top-level
# docs/ and referenced it by path+hash from its own snapshot; this tool follows that identical
# path+hash-reference pattern, just pointed at the in-directory files).
PROTOCOL_ROLES = {
    "study_protocol": "studies/study02/STUDY_02_PROTOCOL.md",
    "analysis_plan": "studies/study02/STUDY_02_ANALYSIS_PLAN.md",
    "execution_policy": "studies/study02/STUDY_02_EXECUTION_POLICY.md",
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


def build_payload() -> dict:
    config = S.SeriesConfig.from_json(HERE / "series.json")
    spec = _load_json(HERE / "spec.json")
    sched = _load_json(HERE / "schedule.json")
    spec_by_task = {t["task_id"]: t for t in spec["tasks"]}
    routing = {r["task_id"]: r["claude_md_hash"] for r in spec["treatment"]["claude_md_routing"]}

    tasks = []
    for pkg in sorted(config.packages(), key=lambda p: p.task_id):
        tasks.append({
            "task_id": pkg.task_id, "repository_family": FAMILY_OF[pkg.task_id],
            "language": pkg.language, "task_category": pkg.task_category,
            "package_dir": _rel(pkg.root),
            "task_version_hash": pkg.version_hash(), "statement_hash": pkg.statement_hash,
            "evaluator_identity": pkg.evaluator_identity(),
            "generated_outputs": list(pkg.generated_outputs),
            "claude_md_hash": routing[pkg.task_id],
            "gate_status": spec_by_task[pkg.task_id]["gate_status"],
        })

    treatment_files = {}
    for fname in sorted({v for v in {"claude_md_S2-PY-A.md": 1, "claude_md_S2-PY-B.md": 1,
                                     "claude_md_S2-PY-C.md": 1, "claude_md_S2-TS-A.md": 1,
                                     "claude_md_S2-TS-B.md": 1, "claude_md_S2-TS-C.md": 1}}):
        treatment_files[fname] = _file_id(f"treatments/study02-v1/{fname}")

    payload = {
        "schema": SNAPSHOT_SCHEMA,
        "study_id": "study02",
        "hash_rule": HASH_RULE,
        "protocol": {
            "roles": {role: _file_id(rel) for role, rel in sorted(PROTOCOL_ROLES.items())},
            "amendments_in_force": [],
        },
        "harness": {
            "harness_git_sha": HARNESS_GIT_SHA,
            "study02_implementation_git_sha": STUDY02_IMPLEMENTATION_GIT_SHA,
            "toolchain": spec["toolchain"],
            "envelope": spec["envelope"],
        },
        "evaluator_identity_rule": (
            "A task's binding evaluator identity is its evaluator_identity + harness_git_sha. "
            "Runtime sandbox policy_hash values contain absolute paths and are provenance only, "
            "never a snapshot key."),
        "treatments": {
            "policy": ("Explicit per-task routing (Gate 7E/7F/7G): six repository-family-specific "
                       "CLAUDE.md files, one per family, two tasks per family receiving byte-"
                       "identical treatment; shared planning_wrapper/approval_message across all "
                       "12 tasks and both configurations; no treatment tuning"),
            "claude_md_family_files": treatment_files,
            "planning_wrapper": _file_id("treatments/study02-v1/planning_wrapper.txt"),
            "approval_message": _file_id("treatments/study02-v1/approval_message.txt"),
            "spec_treatment_hashes": spec["treatment"],
            "canonical_task_treatment_mapping": sorted(
                ({"task_id": tid, "claude_md_hash": h} for tid, h in routing.items()),
                key=lambda r: r["task_id"]),
            "canonical_task_treatment_mapping_hash": canonical_json_hash(
                sorted(({"task_id": tid, "claude_md_hash": h} for tid, h in routing.items()),
                       key=lambda r: r["task_id"])),
        },
        "execution": {
            "model_request": spec["model_request"],
            "model_rule": ("requested model identity; the observed model is checked per "
                           "invocation and a mismatch fails closed (invalid:harness); no silent "
                           "fallback"),
            "effort_request": spec["effort_request"],
            "timeout_seconds": spec["timeout_seconds"],
            "c2_deadline": ("one shared deadline across C2 phase 1 + phase 2; phase 2 receives "
                            "the remainder, never a fresh 900 s; the inter-phase gap is not "
                            "charged"),
        },
        "tasks": tasks,
        "analysis": {
            "research_question": (
                "Under an identical frozen repository CLAUDE.md for each task and fully "
                "candidate-visible task constraints, does the explicit two-phase plan-then-"
                "approve workflow (C2) change contract-compliant task completion relative to "
                "the same substantive CLAUDE.md without that workflow (C1) on a new set of 12 "
                "distinct coding tasks across six repository families?"),
            "primary_unit": "task (12 units; repository-family sharing is a stated structural "
                            "limitation, not an independence claim -- 12 nested, non-independent "
                            "task units, less inferentially supportable than Study-01's 6-task "
                            "design, stated plainly in reporting)",
            "primary_endpoint": {
                "name": "resolved",
                "definition": "valid AND acceptance=pass AND regression=pass AND integrity=clean, "
                              "scored only on countable observations",
            },
            "secondary_endpoints_preregistered": [
                "functional_pass (valid AND acceptance=pass AND regression=pass; integrity "
                "reported separately, remains part of primary resolved)",
                "acceptance", "regression", "integrity",
                "total candidate time", "C2 phase-1 candidate time", "C2 phase-2 candidate time",
                "task-level resolved count out of 2", "paired task x repetition transitions",
            ],
            "exploratory_only": ["language patterns", "task-type patterns",
                                 "repository-family patterns", "repetition variability",
                                 "resolved-only timing if later reported"],
            "excluded": ["token/API-cost metrics", "weighted/composite score (a.k.a. weighted "
                        "quality score)", "generic quality proxies"],
            "token_usage": "EXCLUDED FROM FORMAL STUDY-02 METRICS, matching Study-01's S10 rule",
            "unnecessary_change_rubric": "EXCLUDED FROM FORMAL STUDY-02 METRICS; no frozen "
                                         "rubric; no weighted or composite quality score",
            "replacement_policy": {
                "rule": ("series.replacement_decision, unchanged from Study-01: countable -> "
                         "complete, no replacement; evaluation_pending -> evaluator re-evaluation "
                         "on the preserved final working copy, never an agent rerun; external "
                         "interruption / invalid:infrastructure / invalid:harness / "
                         "preflight_failed -> operator-approved replacement only; invalid:fixture "
                         "-> operator confirmation required, distinct from automatic replacement; "
                         "invalid:leak / invalid:carryover -> series halt; at most one "
                         "replacement per cell; no outcome-quality reruns; every attempt "
                         "preserved; replacements never increase planned N"),
                "ordering": ("approved replacement attempts run only after all 48 planned "
                             "original cells have been attempted, in schedule order "
                             "(Series._next), never at the end of the current block"),
                "spec_replacement_policy": spec["replacement_policy"],
            },
            "agent_time_binding": {
                "c1": "process.json -> elapsed_seconds",
                "c2_phase1": "c2.json -> phases[label == 'phase1'].process.elapsed_seconds",
                "c2_phase2": ("c2.json -> phases[label == 'phase2'].process.elapsed_seconds; not "
                              "started is reported as not started, never 0"),
                "c2_total": "phase1 + phase2 agent elapsed (phase 1 only if phase 2 did not start)",
                "excluded": ("c2.json.inter_phase_gap_seconds; evaluator, cleanup and lifecycle "
                             "time; result.json.duration_seconds and "
                             "c2.json.phases[].duration_seconds are not the performance metric"),
                "timeout": ("result.json agent_outcome == 'timeout' with run_validity == "
                            "'valid' is valid, countable, unsuccessful unless another "
                            "independent validity problem exists"),
            },
            "results_presentation": {
                "key_rules": [
                    "task-by-task results first",
                    "planned-cell denominator: R resolved . F failed . M no countable observation / N planned",
                    "separate attempt / replacement / non-countable accounting",
                    "24 planned cells per configuration, 48 overall",
                    "48 planned cells does not necessarily imply 48 countable observations",
                    "primary contrast C2 - C1",
                    "agent time over all countable attempts with success/failure/timeout visible",
                    "C2 phase 1 + phase 2 breakdown and total",
                    "no weighted composite score",
                    "no significance or generalization claim unsupported by the 12-task, "
                    "6-family design",
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
        "planned_operational_series_root": PLANNED_OPERATIONAL_SERIES_ROOT,
        "planned_operational_series_root_note": "not yet created; no Study-02 production "
                                                "execution has occurred as of this freeze",
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
    if set(spec["configurations"]) != {"C1", "C2"}:
        errors.append("configurations are not exactly C1/C2 (no C0, no C3)")
    if len(cells) != 48 or [c["position"] for c in cells] != list(range(1, 49)):
        errors.append("schedule does not have positions 1..48")
    if len(tasks) != 12 or any(t.startswith("P-") for t in tasks):
        errors.append("task set is not twelve FINAL tasks")
    if set(Counter(c["task_id"] for c in cells).values()) != {4}:
        errors.append("each task must appear 4 times (2 configurations x 2 repetitions)")
    if Counter(c["configuration"] for c in cells) != {"C1": 24, "C2": 24}:
        errors.append("each configuration must appear 24 times")
    pairs = {}
    for c in cells:
        pairs.setdefault((c["task_id"], c["configuration"]), []).append(c["repetition"])
    if len(pairs) != 24 or any(sorted(r) != [1, 2] for r in pairs.values()):
        errors.append("each task x configuration needs repetitions 1, 2 exactly once")
    if len({c["cell_id"] for c in cells}) != 48:
        errors.append("cell_ids are not unique")
    if any(c["task_version_hash"] != tasks[c["task_id"]] for c in cells):
        errors.append("a cell does not point to the frozen task version")
    if any(c["cell_id"] != S.cell_id_for(spec, {"task_id": c["task_id"],
                                                 "task_version_hash": c["task_version_hash"]},
                                          c["configuration"], c["repetition"]) for c in cells):
        errors.append("a cell_id does not recompute")
    routing = spec["treatment"].get("claude_md_routing")
    if not routing or len(routing) != 12:
        errors.append("claude_md_routing does not have exactly 12 entries")
    elif len({r["claude_md_hash"] for r in routing}) != 6:
        errors.append("claude_md_routing does not resolve to exactly 6 distinct family hashes")


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
    ap.add_argument("--snapshot", type=Path, default=HERE / "snapshot.json")
    args = ap.parse_args(argv)

    if args.action == "rehash":
        return rehash(args.snapshot)

    errors: list = []
    check_series(errors)
    payload = build_payload()
    check_tasks(payload, errors)
    check_payload_content(payload, errors)

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
