"""G5s WSL behavioral probe: the real evaluator srt sandbox against the security fixture.

Model-free; run as ``cclab`` from the repository root:

    PYTHONPATH=src:tests python3 spike/g5s-evaluator-sandbox/g5s_probe.py

Prints a JSON report: sandbox startup, filesystem matrix, network, process control, canary
integrity, policy hash, residue. Never opens the real credential file.
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]

from _evsec import EvsecLayout, parse_probe  # noqa: E402

from codeagent_configlab.task_evaluator import CheckSpec, TaskEvaluator  # noqa: E402


def _alive(marker: str) -> list:
    out = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            if marker.encode() in Path(f"/proc/{pid}/cmdline").read_bytes():
                out.append(int(pid))
        except OSError:
            pass
    return out


def main() -> int:
    tmp_before = sorted(os.listdir("/tmp"))
    L = EvsecLayout()
    report = {}
    try:
        before = L.protected_snapshot()
        sb = L.sandbox()
        res = TaskEvaluator(L.spec(), sandbox=sb).evaluate(L.candidate)
        time.sleep(0.3)
        after = L.protected_snapshot()
        py = parse_probe(res, "probe-py", "PROBE:")
        node = parse_probe(res, "probe-node", "NODEPROBE:")
        report["sandbox_startup"] = {"evaluator_error": res.evaluator_error, "detail": res.detail,
                                     "record_kind": res.sandbox.get("kind")}
        report["checks"] = {c["name"]: [c["kind"], c["status"]] for c in res.checks}
        report["filesystem_matrix_python"] = {k: v["ok"] for k, v in sorted(py.items())
                                              if not k.startswith("net:")}
        report["listings"] = {k: py[k]["detail"] for k in py if k.startswith("listdir:")}
        report["node_matrix"] = {k: v["ok"] for k, v in sorted(node.items())}
        report["network"] = {"python_connect_ok": py["net:local_listener"]["ok"],
                             "python_unix_socket_ok": py["net:unix_socket"]["ok"],
                             "node_connect_ok": node["net:local_listener"]["ok"],
                             "listener_connections": L.listener.connections}
        report["canary_integrity"] = {"host_state_identical": before == after,
                                      "canonical_has_hidden_dir":
                                          (L.candidate / "_hidden_tests").exists()}
        report["policy"] = {"hash": sb.policy.policy_hash(), "version": res.sandbox.get("version")}

        marker = f"g5s-probe-grandchild-{uuid.uuid4().hex}"
        code = ("import signal, subprocess, sys, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                "subprocess.Popen([sys.executable, '-c', 'import signal,time;"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)', "
                f"'{marker}'], start_new_session=True)\ntime.sleep(300)\n")
        t0 = time.monotonic()
        r = TaskEvaluator(L.spec(acceptance=(CheckSpec("hang", ("python3", "-c", code, marker), 2.0),)),
                          sandbox=L.sandbox()).evaluate(L.candidate)
        c = next(c for c in r.checks if c["name"] == "hang")
        time.sleep(0.5)
        report["process_control"] = {"status": c["status"], "timed_out": c["timed_out"],
                                     "evaluator_error": r.evaluator_error,
                                     "elapsed_s": round(time.monotonic() - t0, 2),
                                     "survivors": _alive(marker)}
    finally:
        L.cleanup()
    report["residue"] = {"probe_root_exists": L.root.exists(),
                         "other_eval_exists": L.other_eval.exists(),
                         "tmp_claude_canary_exists": L.tmp_claude_canary.exists(),
                         "new_tmp_entries": sorted(set(os.listdir("/tmp")) - set(tmp_before))}
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
