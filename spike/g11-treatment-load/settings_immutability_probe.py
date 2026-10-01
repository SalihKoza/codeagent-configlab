"""G11 model-free probe: <wc>/.claude is immutable under the real outer srt `impl` config.

Run as cclab under WSL (no Claude call):
    PYTHONPATH=<repo>/src python3 spike/g11-treatment-load/settings_immutability_probe.py

The whole `claude` process -- including its built-in Read/Edit/Write tools -- runs inside this
same outer sandbox, so a Node `fs` write here exercises the same kernel enforcement those tools
hit. Model-controlled Bash additionally runs under the inner sandbox (checked in the one-call
smoke).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from codeagent_configlab.envelope import SecurityPolicy
from codeagent_configlab.runners import _resolve_exe
from codeagent_configlab.workspace import make_working_copy

HOME = os.path.expanduser("~")
root = Path(HOME) / "cclab-g11-probe"
shutil.rmtree(root, ignore_errors=True)
pristine = root / "pristine"
pristine.mkdir(parents=True)
(pristine / "calc.py").write_text("def add(a, b):\n    return a + b\n")
wc = make_working_copy(pristine, root / "runs", seed_settings=True, git_baseline=True).path
Path("/tmp/claude").mkdir(mode=0o700, parents=True, exist_ok=True)
run_tmp = tempfile.mkdtemp(dir=str(root))
cfg = Path(run_tmp) / "outer-srt.json"
cfg.write_text(json.dumps(SecurityPolicy().render_outer_srt("impl", HOME, str(root / "harness-root-stand-in"),
                                                          str(wc), run_tmp)))
srt = _resolve_exe("srt", HOME)
node = shutil.which("node") or str(Path(srt).parent / "node")
env = dict(os.environ, TMPDIR=run_tmp, PATH=str(Path(srt).parent) + ":" + os.environ.get("PATH", ""))


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


before = {n: digest(wc / ".claude" / n) for n in ("settings.json", "settings.local.json")}

probes = {
    "bash_redirect": ["sh", "-c", "printf x >> .claude/settings.json"],
    "bash_overwrite_local": ["sh", "-c", "echo '{\"hooks\":{}}' > .claude/settings.local.json"],
    "python_write": [sys.executable, "-c", "open('.claude/settings.json','a').write('x')"],
    "node_write": [node, "-e", "require('fs').appendFileSync('.claude/settings.json','x')"],
    "create_agent": ["sh", "-c", "mkdir -p .claude/agents && echo x > .claude/agents/a.md"],
    "write_into_seeded_commands": ["sh", "-c", "echo x > .claude/commands/c.md"],
    "create_rules": ["sh", "-c", "mkdir -p .claude/rules && echo x > .claude/rules/r.md"],
    "create_claude_md_in_dot_claude": ["sh", "-c", "echo x > .claude/CLAUDE.md"],
    "delete_settings": ["sh", "-c", "rm -f .claude/settings.json"],
    "rename_dot_claude": ["sh", "-c", "mv .claude .claude_old"],
    "delete_dot_claude": ["sh", "-c", "rm -rf .claude"],
    "wc_source_write": ["sh", "-c", "echo 'X = 1' > new_module.py"],
}
results = {}
for name, argv in probes.items():
    p = subprocess.run([srt, "-s", str(cfg), "--", *argv], cwd=str(wc), env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    results[name] = {"rc": p.returncode, "stderr": p.stderr.decode(errors="replace").strip()[-160:]}

after = {n: digest(wc / ".claude" / n) for n in ("settings.json", "settings.local.json")}
extra = sorted(str(p.relative_to(wc)) for p in (wc / ".claude").rglob("*")) if (wc / ".claude").exists() else None
ok = (
    before == after
    and extra == [".claude/agents", ".claude/commands", ".claude/settings.json", ".claude/settings.local.json"]
    and all(results[k]["rc"] != 0 for k in probes if k != "wc_source_write")
    and results["wc_source_write"]["rc"] == 0 and (wc / "new_module.py").exists()
)
print(json.dumps({"results": results, "settings_unchanged": before == after, "dot_claude_contents": extra},
                 indent=1))
shutil.rmtree(root, ignore_errors=True)
print("G11_IMMUTABILITY_PROBE_OK" if ok else "G11_IMMUTABILITY_PROBE_FAIL")
