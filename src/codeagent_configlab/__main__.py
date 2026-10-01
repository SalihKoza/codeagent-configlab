"""Minimal operator CLI. The ONLY runnable command is the harness smoke gate.

Deliberately narrow so a final benchmark run cannot be started by accident: there is no
``run-benchmark`` / ``final`` command here. The real Claude call happens only with an explicit
``--run`` (default is ``--dry``, which exercises everything except the model call).

    python -m codeagent_configlab smoke --dry                 # offline preview
    python -m codeagent_configlab smoke --run                 # one real HARNESS_SMOKE_ONLY call
    python -m codeagent_configlab smoke --run --model haiku --root ~/cclab-harness-smoke

Pilot series (G10, docs/PILOT_SERIES_V0.md). Everything except ``run-next --execute`` is
model-free; ``run-next`` refuses unless the frozen series is ready (model, effort, timeout,
treatment, gate-passed packages) and runs exactly ONE attempt:

    python -m codeagent_configlab series freeze  --config series.json --harness-root ~/cclab-pilot
    python -m codeagent_configlab series status  --config series.json --harness-root ~/cclab-pilot
    python -m codeagent_configlab series plan    --config series.json --harness-root ~/cclab-pilot
    python -m codeagent_configlab series approve-replacement --cell <id> --reason "..." ...
    python -m codeagent_configlab series recover --attempt <run_id> ...
    python -m codeagent_configlab series reevaluate --attempt <run_id> ...
    python -m codeagent_configlab series run-next --execute ...
    python -m codeagent_configlab series remediate-cleanup --attempt <run_id> --reason "..." ...
    python -m codeagent_configlab series resume --reason "..." ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .smoke import DEFAULT_EFFORT, DEFAULT_MODEL, SMOKE_NAMESPACE, run_smoke


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codeagent_configlab", description=f"{SMOKE_NAMESPACE} harness gate")
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("smoke", help="run ONE HARNESS_SMOKE_ONLY C0 run (not a benchmark)")
    smoke.add_argument("--root", default=None, help="harness root dir (default ~/cclab-harness-smoke)")
    smoke.add_argument("--model", default=DEFAULT_MODEL, help="provisional infra model (NOT the final pin)")
    smoke.add_argument("--effort", default=DEFAULT_EFFORT,
                       help="provisional infra effort (NOT the frozen pilot effort_request)")
    smoke.add_argument("--home", default="/home/cclab")
    smoke.add_argument("--uid", type=int, default=1001)
    mode = smoke.add_mutually_exclusive_group()
    mode.add_argument("--run", dest="dry", action="store_false", help="make the one real Claude call")
    mode.add_argument("--dry", dest="dry", action="store_true", help="offline preview (default)")
    smoke.set_defaults(dry=True)

    ser = sub.add_parser("series", help="pilot-series driver (G10); one attempt per run-next")
    ser.add_argument("action", choices=["freeze", "status", "plan", "approve-replacement",
                                        "recover", "reevaluate", "run-next", "remediate-cleanup",
                                        "resume"])
    ser.add_argument("--config", required=True, help="series config JSON (operator-authored)")
    ser.add_argument("--harness-root", required=True)
    ser.add_argument("--home", default="/home/cclab")
    ser.add_argument("--uid", type=int, default=1001)
    ser.add_argument("--cell")
    ser.add_argument("--attempt")
    ser.add_argument("--reason", default="")
    ser.add_argument("--note", default="")
    ser.add_argument("--execute", action="store_true",
                     help="run-next only: really start the next attempt (real Claude call)")

    args = parser.parse_args(argv)
    if args.command == "series":
        return _series(args)
    if args.command == "smoke":
        summary = run_smoke(
            harness_root=Path(args.root).expanduser() if args.root else None,
            model=args.model, effort=args.effort, dry=args.dry, home=args.home, uid=args.uid,
        )
        print(json.dumps(summary, indent=2))
        res = summary.get("result")
        if isinstance(res, str):  # BLOCKED_*
            return 2
        if isinstance(res, dict) and res.get("run_validity") != "valid":
            return 1
        return 0
    return 2


def _series(args) -> int:
    from .series import Series, SeriesConfig, SeriesError

    config = SeriesConfig.from_json(args.config)
    harness = Path(args.harness_root).expanduser()
    series = Series(root=harness / "series" / config.pilot_version, config=config,
                    harness_root=harness, home=Path(args.home), uid=args.uid)
    try:
        if args.action == "freeze":
            out = series.freeze()
        elif args.action == "status":
            out = series.status()
        elif args.action == "plan":
            out = series.plan_next()
        elif args.action == "approve-replacement":
            out = series.approve_replacement(args.cell, args.reason, args.note)
        elif args.action == "recover":
            out = series.recover(args.attempt)
        elif args.action == "reevaluate":
            out = series.reevaluate(args.attempt, _production_evaluator(series, args.attempt))
        elif args.action == "remediate-cleanup":
            cleanup_report = _run_post_hoc_cleanup(series, args)
            out = series.remediate_cleanup(args.attempt, cleanup_report=cleanup_report,
                                           reason=args.reason)
            if cleanup_report.get("cleanup_failed") or not cleanup_report.get("residue", {}).get(
                    "all_clear", True):
                print(json.dumps({"warning": "post-hoc cleanup did not fully succeed; manual "
                                             "operator follow-up is still required",
                                  "cleanup_report": cleanup_report}, indent=2))
        elif args.action == "resume":
            out = series.resume(reason=args.reason, note=args.note)
        elif args.action == "run-next":
            if not args.execute:
                print(json.dumps({"refused": "run-next needs --execute (it starts a real Claude "
                                             "attempt); use 'plan' for a dry run"}, indent=2))
                return 2
            out = series.execute_next(*_production_factories(series, args),
                                      cleanup_runner=_production_cleanup_runner(series, args))
        else:
            return 2
    except SeriesError as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}, indent=2))
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0


def _package(series, task_id):
    return next(p for p in series.config.packages() if p.task_id == task_id)


def _evaluator_for(series, pkg):
    from .evaluator_sandbox import production_evaluator_sandbox
    from .task_evaluator import TaskEvaluator

    spec = pkg.evaluator_spec()
    return TaskEvaluator(spec, sandbox=production_evaluator_sandbox(
        spec, harness_root=str(series.harness_root), results_root=str(series.attempts_root)))


def _production_factories(series, args):
    """Real runner/evaluator built ONLY from the attempt manifest / task package (no extra
    timeout or model: the lifecycle takes the budget from the manifest)."""
    from .runners import RealAgentRunner

    def runner_factory(manifest):
        return RealAgentRunner(home=args.home, harness_root=str(series.harness_root),
                               model=manifest.model_request, effort=manifest.effort_request,
                               prompt=_package(series, manifest.task_id).statement())

    return runner_factory, lambda pkg: _evaluator_for(series, pkg)


def _production_cleanup_runner(series, args):
    """The real, scope-guarded cleanup runner -- always constructed explicitly for real execution
    so ``series.execute_next`` can never again silently fall back to the offline DryCleanupRunner."""
    from .runners import RealCleanupRunner

    return RealCleanupRunner(home=args.home)


def _production_evaluator(series, attempt_id):
    import json as _json

    manifest = _json.loads((series.attempts_root / attempt_id / "manifest.json").read_text())
    return _evaluator_for(series, _package(series, manifest["task_id"]))


def _run_post_hoc_cleanup(series, args) -> dict:
    """Run the exact, unmodified, scoped cleanup mechanism against an already-finished attempt
    whose original cleanup never ran (the historical wiring defect), for ``remediate-cleanup``.

    Uses the same ``build_cleanup_plan`` inputs the original attempt would have used (its own
    working copy path and observed session id) -- nothing new is invented. Returns a report dict
    combining the real execution result with a post-hoc residue verification; recorded only on the
    new ``cleanup_remediated`` event, never overwriting the attempt's original ``cleanup.json``.
    """
    from .cleanup import build_cleanup_plan, verify_residue
    from .runners import RealCleanupRunner

    run_dir = series.attempts_root / args.attempt
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    wc = series.runs_root / manifest["workspace_token"]
    session_ids = [result["observed_session_id"]] if result.get("observed_session_id") else []
    plan = build_cleanup_plan(str(wc), session_ids, uid=args.uid, home=args.home)
    report = RealCleanupRunner(home=args.home).execute(plan)
    report["residue"] = verify_residue(plan, home=args.home)
    return report


if __name__ == "__main__":
    sys.exit(main())
