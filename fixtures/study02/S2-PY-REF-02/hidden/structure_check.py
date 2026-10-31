"""Lightweight AST-based structural check for S2-PY-REF-02.

Rules (deliberately small and permissive of legitimate alternative implementations):
  R1. buckets.py defines at least one class (plain class or @dataclass) - i.e. per-client
      bucket state is represented by a named structure, not only bare dict literals.
  R2. The refill/consume logic (allow/configure/reset functions) does not access bucket
      state via string-keyed subscript (e.g. bucket["tokens"]) anymore - i.e. it has moved
      to attribute access on the new structure.

Exit codes: 0 = all rules pass, 1 = a rule failed, 3 = internal checker error.
"""
import ast
import json
import sys
from pathlib import Path


def main():
    try:
        # cwd is always the working-copy root (either the real sandbox or our own
        # direct-invocation validation script), so the package source is always here.
        src_path = Path.cwd() / "throttlekit" / "buckets.py"
        source = src_path.read_text()
        tree = ast.parse(source, filename=str(src_path))
    except Exception as exc:  # pragma: no cover - internal checker error path
        print(json.dumps({"error": f"internal checker error: {exc}"}))
        return 3

    rules = {}

    # R1: at least one class definition exists in buckets.py.
    class_defs = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    rules["R1_class_defined"] = len(class_defs) >= 1

    # R2: no string-keyed subscript access on a name that looks like bucket state
    # (heuristic: any Subscript node whose slice is a string constant key that matches
    # one of the known field names, applied to a Name/Attribute base - this is the
    # old dict-access pattern this refactor is meant to eliminate).
    field_names = {"tokens", "last_refill", "rate", "burst"}
    offending = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value in field_names:
                    offending.append(key.value)
    rules["R2_no_dict_key_access_on_fields"] = len(offending) == 0

    report = {"rules": rules, "offending_keys": offending, "pass": all(rules.values())}
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
