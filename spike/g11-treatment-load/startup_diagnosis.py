"""Model-free startup diagnosis for the G11 envelope (no inference).

Each variant runs the real `srt -- claude -p ...` argv built by RealAgentRunner, but with a
whitespace-only prompt: 2.1.263 then stops with "Input contained only whitespace" before any API
request. A different error means startup itself failed for that variant.
"""
import dataclasses
import json
import os
import shutil
from pathlib import Path

from codeagent_configlab.envelope import SecurityPolicy, implementation_envelope
from codeagent_configlab.runners import RealAgentRunner
from codeagent_configlab.session import SessionSpec, new_session_uuid
from codeagent_configlab.treatment import Treatment, materialize_treatment
from codeagent_configlab.workspace import make_working_copy
from codeagent_configlab.cleanup import build_cleanup_plan
from codeagent_configlab.runners import RealCleanupRunner

HOME = os.path.expanduser("~")
ROOT = Path(HOME) / "cclab-g11-diag"


def variant(name, loader, protect):
    policy = SecurityPolicy(protected_wc_subpaths=(".claude",) if protect else ())
    env = dataclasses.replace(implementation_envelope("C1", policy),
                              instruction_loader="add_dir_claude_md" if loader else "none")
    wc = make_working_copy(ROOT / "pristine", ROOT / "runs", seed_settings=True, git_baseline=True)
    materialize_treatment(wc.path, "C1", Treatment(claude_md=b"# diag\n"))
    uuid = new_session_uuid()
    r = RealAgentRunner(home=HOME, harness_root=str(ROOT), model="haiku", effort="high",
                        prompt=" ", tmp_root=str(ROOT / "tmp"), timeout=60)
    out = r.run(wc, env, SessionSpec("new", uuid))
    RealCleanupRunner(home=HOME).execute(build_cleanup_plan(str(wc.path), [uuid], uid=os.getuid(), home=HOME))
    return {"variant": name, "exit": out.exit_code, "outcome": out.agent_outcome.value,
            "events": len(out.events), "stdout_tail": out.stdout[-400:], "stderr_tail": out.stderr[-600:]}


shutil.rmtree(ROOT, ignore_errors=True)
(ROOT / "pristine").mkdir(parents=True)
(ROOT / "pristine" / "calc.py").write_text("x = 1\n")
Path("/tmp/claude").mkdir(mode=0o700, parents=True, exist_ok=True)
res = [variant("pre-G11 (no loader, no .claude protect)", False, False),
       variant("protect only", False, True),
       variant("loader only", True, False),
       variant("G11 full (loader + protect)", True, True)]
shutil.rmtree(ROOT, ignore_errors=True)
print(json.dumps(res, indent=1))
