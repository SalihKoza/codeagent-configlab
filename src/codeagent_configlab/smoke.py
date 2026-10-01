"""HARNESS_SMOKE_ONLY: one disposable C0 run that proves the harness works under WSL.

This is **not** a pilot and **not** one of the six final tasks. It exists only to exercise the
real execution path (prepare -> preflight -> agent -> capture -> evaluate -> capture -> purge ->
exact cleanup) once, end to end, as `cclab`. The fixture is `fixtures/harness-smoke`; the model
is a provisional infrastructure value (default ``haiku``) that does NOT freeze the final model
pin (O5). Everything except the single Claude call is offline and re-checkable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .artifacts import ArtifactStore
from .envelope import SecurityPolicy, implementation_envelope
from .evaluator import SmokeEvaluator
from .hashing import canonical_json_hash, sha256_text
from .ids import new_run_id, new_workspace_token
from .lifecycle import DryAgentRunner, DryCleanupRunner, RunLifecycle
from .manifest import RunManifest
from .preflight import run_start_checks
from .runners import RealAgentRunner, RealCleanupRunner, _resolve_exe
from .session import SessionSpec, new_session_uuid
from .workspace import make_working_copy

SMOKE_NAMESPACE = "HARNESS_SMOKE_ONLY"
SMOKE_TASK_ID = "HARNESS-SMOKE-C0"
DEFAULT_MODEL = "haiku"  # provisional infra model; NOT the frozen O5 pin
DEFAULT_EFFORT = "high"  # provisional infra effort; NOT the frozen pilot effort_request
DEFAULT_HARNESS_ROOT = "~/cclab-harness-smoke"

SMOKE_STATEMENT = (
    "This is an automated harness smoke test (HARNESS_SMOKE_ONLY), not a real task.\n"
    "In calc.py, add a function `multiply(a, b)` that returns a * b. Keep the existing `add` "
    "function unchanged. Make only that edit."
)


def default_harness_root() -> Path:
    return Path(os.path.expanduser(DEFAULT_HARNESS_ROOT))


def build_smoke_manifest(model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT) -> RunManifest:
    """A schema-valid C0 manifest for the smoke run. Explicitly non-final (task id + model)."""
    policy = SecurityPolicy()
    env = implementation_envelope("C0", policy)
    return RunManifest(
        run_id=new_run_id(),
        task_id=SMOKE_TASK_ID,
        task_version_hash=sha256_text("harness-smoke-fixture/v0"),
        language="python",
        task_category="feature",
        configuration="C0",
        repetition=1,
        workspace_token=new_workspace_token(),
        settings_policy_hash=env.envelope_hash(),
        security_policy_hash=policy.policy_hash(),
        task_statement_hash=sha256_text(SMOKE_STATEMENT),
        implementation_tool_set=env.tools,
        model_request=model,  # provisional; does not freeze O5
        effort_request=effort,  # provisional; does not freeze the pilot effort_request
    )


@dataclass
class SmokeLayout:
    root: Path
    fixtures: Path
    pristine: Path
    runs: Path
    tmp: Path
    results: Path
    hidden: Path
    canary: str


def setup_layout(harness_root: Path, repo_fixture: Path) -> SmokeLayout:
    """Create the on-Linux harness layout and a hidden canary. Idempotent for runs/tmp/results."""
    root = harness_root
    fixtures = root / "fixtures" / "harness-smoke"
    runs, tmp, results, hidden = root / "runs", root / "tmp", root / "results", root / "hidden"
    for d in (root, runs, tmp, results, hidden, fixtures.parent):
        d.mkdir(parents=True, exist_ok=True)
    # (re)materialize the pristine fixture on the Linux fs from the repo copy
    if fixtures.exists():
        shutil.rmtree(fixtures)
    shutil.copytree(repo_fixture, fixtures)
    canary = "HARNESS-SMOKE-CANARY-" + os.urandom(8).hex()
    (hidden / "CANARY.txt").write_text(canary + "\n", encoding="utf-8")
    return SmokeLayout(root, fixtures, fixtures, runs, tmp, results, hidden, canary)


def srt_canary_probe(layout: SmokeLayout, home: str) -> dict:
    """Model-free proof that the outer sandbox hides the harness root but exposes the WC.

    Creates a throwaway working copy, renders the outer *impl* srt config, and checks that
    ``cat hidden/CANARY.txt`` is denied while ``cat <wc>/calc.py`` succeeds — the evaluator /
    hidden-material boundary (§10), verified without a model call and without real secrets.
    """
    Path("/tmp/claude").mkdir(mode=0o700, parents=True, exist_ok=True)
    wc = make_working_copy(layout.pristine, layout.runs, seed_settings=True)
    run_tmp = tempfile.mkdtemp(dir=str(layout.tmp))
    policy = SecurityPolicy()
    outer = policy.render_outer_srt("impl", home, str(layout.root), str(wc.path), run_tmp)
    cfg = Path(run_tmp) / "probe-srt.json"
    cfg.write_text(json.dumps(outer), encoding="utf-8")
    srt = _resolve_exe("srt", home)
    env = {k: v for k, v in os.environ.items()}
    env["TMPDIR"] = run_tmp

    def _run(target_argv):
        return subprocess.run([srt, "-s", str(cfg), "--", *target_argv],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    canary_probe = _run(["cat", str(layout.hidden / "CANARY.txt")])
    wc_probe = _run(["cat", str(wc.path / "calc.py")])
    canary_denied = canary_probe.returncode != 0 and layout.canary.encode() not in canary_probe.stdout
    wc_readable = wc_probe.returncode == 0 and b"def add" in wc_probe.stdout
    # tidy the throwaway probe copy
    shutil.rmtree(wc.path, ignore_errors=True)
    shutil.rmtree(run_tmp, ignore_errors=True)
    return {
        "canary_denied": bool(canary_denied),
        "wc_readable": bool(wc_readable),
        "canary_probe_rc": canary_probe.returncode,
        "wc_probe_rc": wc_probe.returncode,
    }


def offline_checks(layout: SmokeLayout, home: str) -> dict:
    """Run all model-free checks that must pass before the real call. Returns a report dict."""
    from . import __version__
    from ._schemas import load_schema
    from .cleanup import build_cleanup_plan

    report: dict = {"ok": False, "checks": {}}
    c = report["checks"]
    c["import_version"] = __version__
    c["schemas_load"] = bool(load_schema("run-manifest.schema.json") and load_schema("run-result.schema.json"))
    pol = SecurityPolicy()
    c["policy_hash"] = pol.policy_hash()
    plan = build_cleanup_plan(str(layout.runs / "deadbeefdeadbeef"), [new_session_uuid()])
    c["cleanup_plan_len"] = len(plan)
    wc = make_working_copy(layout.pristine, layout.runs, seed_settings=True)
    c["workspace_hash_ok"] = bool(wc.baseline_hash)
    shutil.rmtree(wc.path, ignore_errors=True)
    try:
        c["srt_canary_probe"] = srt_canary_probe(layout, home)
        c["srt_available"] = True
    except FileNotFoundError as exc:
        c["srt_available"] = False
        c["srt_error"] = str(exc)
    probe = c.get("srt_canary_probe", {})
    report["ok"] = (
        c["schemas_load"]
        and c["workspace_hash_ok"]
        and c.get("srt_available", False)
        and probe.get("canary_denied", False)
        and probe.get("wc_readable", False)
    )
    return report


def _safe_metadata(manifest: RunManifest, layout: SmokeLayout, preflight_ok: bool) -> dict:
    """Only non-secret metadata (§8). Never env/creds/tokens."""
    return {
        "namespace": SMOKE_NAMESPACE,
        "run_id": manifest.run_id,
        "configuration": manifest.configuration,
        "fixture_id": SMOKE_TASK_ID,
        "requested_model_NON_FINAL": manifest.model_request,
        "workspace_token": manifest.workspace_token,
        "security_policy_hash": manifest.security_policy_hash,
        "manifest_hash": canonical_json_hash(manifest.to_dict()),
        "preflight": "PASS" if preflight_ok else "PENDING",
        "results_dir": str(layout.results / manifest.run_id),
    }


def run_smoke(
    *,
    harness_root: Optional[Path] = None,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    dry: bool = True,
    home: str = "/home/cclab",
    uid: int = 1001,
    repo_fixture: Optional[Path] = None,
) -> dict:
    """Orchestrate one HARNESS_SMOKE_ONLY run. ``dry`` avoids the real Claude call.

    Returns a JSON-safe summary. Prints only safe metadata (never secrets).
    """
    harness_root = Path(harness_root or default_harness_root())
    if repo_fixture is None:
        repo_fixture = Path(__file__).resolve().parents[2] / "fixtures" / "harness-smoke"
    layout = setup_layout(harness_root, repo_fixture)

    summary: dict = {"namespace": SMOKE_NAMESPACE, "dry": dry}

    # 1) offline model-free gate
    off = offline_checks(layout, home)
    summary["offline_checks"] = off
    print(f"[{SMOKE_NAMESPACE}] offline checks: {'PASS' if off['ok'] else 'FAIL'}")
    if not off["ok"]:
        summary["result"] = "BLOCKED_OFFLINE_CHECKS"
        return summary

    # 2) manifest + session
    manifest = build_smoke_manifest(model, effort)
    session = SessionSpec("new", new_session_uuid())
    envelope = implementation_envelope("C0", SecurityPolicy())

    # 3) safe metadata (before the call)
    meta = _safe_metadata(manifest, layout, preflight_ok=True)
    summary["metadata"] = meta
    print(f"[{SMOKE_NAMESPACE}] " + json.dumps(meta))

    # 4) execute the lifecycle
    life = RunLifecycle(
        pristine=layout.pristine, runs_root=layout.runs, results_root=layout.results,
        home=Path(home), uid=uid, harness_root=layout.root,
    )
    if dry:
        agent_runner = DryAgentRunner(mutate=_add_multiply, model=model)
        cleanup_runner = DryCleanupRunner()
    else:
        agent_runner = RealAgentRunner(
            home=home, harness_root=str(layout.root), model=model, effort=effort,
            prompt=SMOKE_STATEMENT, tmp_root=str(layout.tmp), timeout=300,
        )
        cleanup_runner = RealCleanupRunner(home=home)

    result = life.execute(
        manifest=manifest, envelope=envelope, session=session,
        evaluator=SmokeEvaluator(), agent_runner=agent_runner, cleanup_runner=cleanup_runner,
        preflight_checks=run_start_checks(),
    )
    summary["result"] = result.to_dict()

    # 5) post-run secret scan of the whole results dir, including the run's own canary
    store = ArtifactStore(run_dir=layout.results / manifest.run_id)
    leaks = store.scan_dir_for_secrets(extra_markers=(layout.canary,))
    summary["secret_leaks"] = leaks
    print(f"[{SMOKE_NAMESPACE}] run_validity={result.run_validity.value} "
          f"agent_outcome={result.agent_outcome.value} acceptance={result.acceptance.value} "
          f"leaks={'NONE' if not leaks else leaks}")
    return summary


def _add_multiply(wc: Path) -> None:
    """Dry-mode stand-in for what the agent should do (used only when dry=True)."""
    f = wc / "calc.py"
    f.write_text(f.read_text(encoding="utf-8") + "\n\ndef multiply(a, b):\n    return a * b\n", encoding="utf-8")
