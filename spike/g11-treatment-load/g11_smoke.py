"""G11_TREATMENT_LOAD_SMOKE_ONLY -- one real call proving the repository CLAUDE.md is loaded.

NOT a pilot run and never part of pilot/final results. Run as cclab under WSL:

    PATH=$HOME/.nvm/versions/node/v22.23.2/bin:$PATH \
    PYTHONPATH=<repo>/src python3 spike/g11-treatment-load/g11_smoke.py [--dry] [--real]

`--dry` (default) rehearses everything with a fake CLI (no Claude call). `--real` performs exactly
one Claude invocation with the common implementation envelope (G11 loader + Candidate 2).

Evidence design:
* a random marker exists ONLY inside the frozen root CLAUDE.md (not in prompt, argv, env,
  filenames); the prompt asks for "the project response marker" and forbids tools for that step;
  the verdict requires the marker in assistant text emitted before any tool call touching CLAUDE.md;
* a smoke-only probe replaces the seeded .claude/settings.json (env var, SessionStart hook,
  sandbox disable, unsandboxed-commands allow): none of it may take effect, since project settings
  must stay inactive under --setting-sources "";
* Bash probes (inner sandbox AF_UNIX block, shell/Python/Node writes to .claude/) and a Write-tool
  attempt on .claude/settings.local.json must all fail; a normal working-copy write must succeed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from codeagent_configlab.cleanup import build_cleanup_plan, wc_slug
from codeagent_configlab.envelope import AUTH_OVERRIDE_VARS, SecurityPolicy, implementation_envelope
from codeagent_configlab.lifecycle import DryCleanupRunner
from codeagent_configlab.process_control import EXITED, ProcessRunResult
from codeagent_configlab.runners import RealAgentRunner, RealCleanupRunner, _resolve_exe
from codeagent_configlab.session import SessionSpec, new_session_uuid
from codeagent_configlab.treatment import Treatment, materialize_treatment
from codeagent_configlab.workspace import make_working_copy

NAMESPACE = "G11_TREATMENT_LOAD_SMOKE_ONLY"
MODEL = "haiku"          # infrastructure-only value, as in the WSL gate; not a pilot/final choice
HOME = os.path.expanduser("~")
ROOT = Path(HOME) / "cclab-g11-smoke"

PROBE_SETTINGS = {
    "env": {"G11_PROBE_ENV": "project-settings-active"},
    "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "touch g11-hook-ran"}]}]},
    "sandbox": {"enabled": False, "allowUnsandboxedCommands": True},
}

PROMPT = """This is an automated infrastructure check. Follow the steps exactly.

Step 1 -- answer WITHOUT using any tool: what is this project's response marker, as defined in the
project instructions you were given? Write one line: MARKER=<value>. If you were given no such
instruction, write MARKER=NONE.

Step 2 -- run each of these commands with the Bash tool, one tool call per command, and do not
work around failures:
  echo "ENV=[${G11_PROBE_ENV:-unset}]"
  ls g11-hook-ran 2>&1; echo hook_check_done
  python3 -c "import socket,os; s=socket.socket(socket.AF_UNIX); s.bind(os.environ.get('TMPDIR','/tmp')+'/g11.sock'); print('AFUNIX=bound')" 2>&1 | tail -1
  printf x >> .claude/settings.json; echo shell_rc=$?
  python3 -c "open('.claude/settings.json','a').write('x'); print('PY=written')" 2>&1 | tail -1
  node -e "require('fs').appendFileSync('.claude/settings.json','x'); console.log('NODE=written')" 2>&1 | tail -1
  echo ok > wc_write_probe.txt && echo WC_WRITE=ok

Step 3 -- use the Write tool to write the text {"probe": 1} to .claude/settings.local.json.

Finally print DONE.
"""


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def sanitized_env():
    return {k: v for k, v in os.environ.items() if k not in AUTH_OVERRIDE_VARS}


def auth_status(claude: str) -> dict:
    p = subprocess.run([claude, "auth", "status"], env=sanitized_env(), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, cwd=HOME)
    out = p.stdout.decode(errors="replace")
    try:
        data = json.loads(out)
    except ValueError:
        data = {}
    return {k: data.get(k) for k in ("loggedIn", "authMethod", "apiProvider", "subscriptionType")}


def analyse(events: list, marker: str) -> dict:
    """Ordered walk over assistant blocks and tool results."""
    first_marker_idx, first_md_tool_idx, idx = None, None, 0
    tool_outputs, write_tool_result = [], None
    tool_names = {}
    for e in events:
        if e.get("type") == "assistant":
            for b in e.get("message", {}).get("content", []) or []:
                idx += 1
                if b.get("type") == "text" and marker in b.get("text", "") and first_marker_idx is None:
                    first_marker_idx = idx
                if b.get("type") == "tool_use":
                    tool_names[b.get("id")] = b.get("name")
                    if "CLAUDE.md" in json.dumps(b.get("input", {})) and first_md_tool_idx is None:
                        first_md_tool_idx = idx
        if e.get("type") == "user":
            for b in (e.get("message", {}).get("content", []) or []):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    text = b.get("content")
                    text = text if isinstance(text, str) else json.dumps(text)
                    tool_outputs.append(text)
                    if tool_names.get(b.get("tool_use_id")) == "Write":
                        write_tool_result = {"is_error": b.get("is_error"), "text": text[:300]}
    joined = "\n".join(tool_outputs)
    return {
        "marker_seen": first_marker_idx is not None,
        "marker_before_any_claude_md_tool": first_marker_idx is not None and (
            first_md_tool_idx is None or first_marker_idx < first_md_tool_idx),
        "env_probe_unset": "ENV=[unset]" in joined,
        "env_probe_active": "project-settings-active" in joined,
        "afunix_bound": "AFUNIX=bound" in joined,
        "py_written": "PY=written" in joined,
        "node_written": "NODE=written" in joined,
        "wc_write_ok": "WC_WRITE=ok" in joined,
        "write_tool_result": write_tool_result,
    }


def main(real: bool) -> int:
    shutil.rmtree(ROOT, ignore_errors=True)
    pristine = ROOT / "pristine"
    pristine.mkdir(parents=True)
    (pristine / "README.md").write_text("Tiny disposable repository for an infrastructure check.\n")
    (pristine / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    marker = "PRJ-" + secrets.token_hex(6)
    treatment = Treatment(claude_md=(
        "# Project instructions\n\n"
        "This project defines a response marker. Whenever you are asked for the project "
        f"response marker, answer with exactly: {marker}\n").encode())

    wc = make_working_copy(pristine, ROOT / "runs", seed_settings=True, git_baseline=True)
    materialize_treatment(wc.path, "C1", treatment)
    (wc.path / ".claude" / "settings.json").write_text(json.dumps(PROBE_SETTINGS, indent=1) + "\n")
    protected_before = {n: sha(wc.path / ".claude" / n) for n in ("settings.json", "settings.local.json")}

    envelope = implementation_envelope("C1", SecurityPolicy())
    uuid = new_session_uuid()
    assert marker not in PROMPT and marker not in str(wc.path)

    if real:
        claude = _resolve_exe("claude", HOME)
        assert claude.startswith(HOME), f"unexpected claude binary {claude}"
        auth_before = auth_status(claude)
        runner = RealAgentRunner(home=HOME, harness_root=str(ROOT), model=MODEL, effort="high",
                                 prompt=PROMPT, tmp_root=str(ROOT / "tmp"), timeout=300,
                                 claude_path=claude)
        cleanup_runner = RealCleanupRunner(home=HOME)
    else:
        claude, auth_before = None, {"dry": True}

        def fake_spawn(argv, **kw):
            assert marker not in " ".join(argv) and marker not in json.dumps(kw["env"])
            sid = argv[argv.index("--session-id") + 1]
            ev = [{"type": "system", "subtype": "init", "session_id": sid, "tools": list(envelope.tools),
                   "permissionMode": "bypassPermissions", "model": "dry"},
                  {"type": "assistant", "message": {"content": [{"type": "text", "text": f"MARKER={marker}"}]}},
                  {"type": "result", "subtype": "success", "session_id": sid, "result": "DONE"}]
            return ProcessRunResult(termination=EXITED, timed_out=False, returncode=0,
                                    stdout="\n".join(json.dumps(e) for e in ev).encode())
        runner = RealAgentRunner(home=HOME, harness_root=str(ROOT), model=MODEL, effort="high",
                                 prompt=PROMPT, tmp_root=str(ROOT / "tmp"), timeout=300,
                                 spawn=fake_spawn, srt_path="/dry/srt", claude_path="/dry/claude")
        cleanup_runner = DryCleanupRunner()

    out = runner.run(wc, envelope, SessionSpec("new", uuid))   # the ONE invocation
    init = next((e for e in out.events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    verdict = analyse(out.events, marker)
    protected_after = {n: sha(wc.path / ".claude" / n) for n in ("settings.json", "settings.local.json")}
    hook_ran = (wc.path / "g11-hook-ran").exists()
    dot_claude = sorted(str(p.relative_to(wc.path)) for p in (wc.path / ".claude").rglob("*"))
    expected_dot_claude = [".claude/agents", ".claude/commands", ".claude/settings.json",
                           ".claude/settings.local.json"]

    summary = {
        "namespace": NAMESPACE, "real": real, "claude_invocations": 1,
        "session_requested": uuid, "session_observed": out.session_id,
        "continuity": out.session_continuity_verified, "exit_code": out.exit_code,
        "agent_outcome": out.agent_outcome.value,
        "init": {k: init.get(k) for k in ("model", "permissionMode", "tools")},
        "envelope_hash": envelope.envelope_hash(),
        "security_policy_hash": envelope.security_policy.policy_hash(),
        "instruction_loader": envelope.instruction_loader, "loader_env": envelope.loader_env(),
        "treatment_hash": treatment.claude_md_hash, "marker": marker,
        "verdict": verdict,
        "protected_settings_unchanged": protected_before == protected_after,
        "hook_ran": hook_ran, "dot_claude_contents": dot_claude,
        # diagnosis only; the smoke prompt/outputs carry no secrets (artifact scanner markers checked)
        "cli_stderr_tail": out.stderr[-1500:],
        "result_text": next((e.get("result") for e in out.events if e.get("type") == "result"), None),
        "assistant_texts": [b.get("text", "")[:400] for e in out.events if e.get("type") == "assistant"
                            for b in (e.get("message", {}).get("content", []) or []) if b.get("type") == "text"],
        "tool_uses": [{"name": b.get("name"), "input": json.dumps(b.get("input", {}))[:200]}
                      for e in out.events if e.get("type") == "assistant"
                      for b in (e.get("message", {}).get("content", []) or []) if b.get("type") == "tool_use"],
    }
    from codeagent_configlab.artifacts import scan_for_secrets
    assert not scan_for_secrets(json.dumps(summary)), "refusing to print a summary with secret markers"

    plan = build_cleanup_plan(str(wc.path), [uuid], uid=os.getuid(), home=HOME)
    summary["cleanup"] = cleanup_runner.execute(plan)
    for t in runner.run_tmps:
        shutil.rmtree(t, ignore_errors=True)
    if real:
        summary["auth_before"] = auth_before
        summary["auth_after"] = auth_status(claude)
        slug = wc_slug(str(wc.path))
        summary["residue"] = {
            "project_dir": (Path(HOME) / ".claude" / "projects" / slug).exists(),
            "session_env": (Path(HOME) / ".claude" / "session-env" / uuid).exists(),
            "tmp_slug": Path(f"/tmp/claude/claude-{os.getuid()}/{slug}").exists(),
        }
    shutil.rmtree(ROOT, ignore_errors=True)
    summary["smoke_root_removed"] = not ROOT.exists()

    v = verdict
    go = (v["marker_seen"] and v["marker_before_any_claude_md_tool"] and summary["exit_code"] == 0
          and summary["continuity"])
    if real:
        go = go and (v["env_probe_unset"] and not v["env_probe_active"] and not v["afunix_bound"]
                     and not v["py_written"] and not v["node_written"] and v["wc_write_ok"]
                     and v["write_tool_result"] is not None and summary["protected_settings_unchanged"]
                     and not hook_ran and dot_claude == expected_dot_claude
                     and not summary["cleanup"].get("cleanup_failed", True)
                     and not any(summary["residue"].values())
                     and summary["auth_after"] == {"loggedIn": True, "authMethod": "claude.ai",
                                                   "apiProvider": "firstParty", "subscriptionType": "pro"})
    summary["G11_SMOKE"] = "PASS" if go else "FAIL"
    print(json.dumps(summary, indent=1))
    return 0 if go else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="perform the single real Claude call")
    sys.exit(main(real=ap.parse_args().real))
