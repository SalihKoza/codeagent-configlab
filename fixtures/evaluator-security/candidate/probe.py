"""Harmless evaluator-sandbox probe (agent-written code stand-in). Prints one JSON line.

Never prints file contents: a successful read reports only its length and whether a canary token
was present.
"""
import hashlib, json, os, socket, subprocess, sys, tempfile

T = json.load(open("targets.json"))
out = {}


def rec(key, fn):
    try:
        out[key] = {"ok": True, "detail": fn()}
    except Exception as exc:  # noqa: BLE001 - every failure is a probe result
        out[key] = {"ok": False, "detail": type(exc).__name__}


def read(path):
    data = open(path, "rb").read()
    return {"len": len(data), "canary": b"CANARY" in data}


def append(path):
    with open(path, "ab") as fh:
        fh.write(b"EVAL-TAMPER\n")
    return "appended"


def create_in(directory):
    p = os.path.join(directory, "EVAL_PLANTED.txt")
    open(p, "w").write("planted")
    return p


def listdir(path):
    return sorted(os.listdir(path))[:20]


# allowed: evaluator copy + private tmp + child processes
rec("copy_write", lambda: open("probe_written.txt", "w").write("x"))
rec("copy_read", lambda: open("probe_written.txt").read())
rec("tmp_write", lambda: tempfile.mkstemp()[1].startswith(os.environ.get("TMPDIR", "?")))
rec("child_process", lambda: subprocess.run([sys.executable, "-c", "print('kid')"],
                                            capture_output=True, check=True).stdout.decode().strip())
rec("hidden_injected_in_copy", lambda: os.path.exists("_hidden_tests/check_hidden.py"))
for name, path in T["read"].items():
    rec("read:" + name, lambda p=path: read(p))
for name, path in T["append"].items():
    rec("append:" + name, lambda p=path: append(p))
for name, path in T["create_in"].items():
    rec("create_in:" + name, lambda p=path: create_in(p))
for name, path in T["listdir"].items():
    rec("listdir:" + name, lambda p=path: listdir(p))
for name, path in T["exists"].items():
    out["exists:" + name] = {"ok": os.path.exists(path), "detail": "stat only"}


def connect():
    s = socket.create_connection(("127.0.0.1", T["port"]), timeout=3)
    s.sendall(b"EVAL-NET")
    s.close()
    return "connected"


rec("net:local_listener", connect)
rec("net:unix_socket", lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).close())
print("PROBE:" + json.dumps(out, sort_keys=True))
