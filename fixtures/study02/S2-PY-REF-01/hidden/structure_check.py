"""Lightweight AST-based structural check for S2-PY-REF-01.

Rules (deliberately small and permissive of legitimate alternative implementations):
  R1. layers.py defines at least one class (plain class or @dataclass) used for layer storage.
  R2. resolve.py no longer accesses a layer's fields via string-keyed subscript
      (the old `layer["data"]` / `layer["name"]` / `layer["precedence"]` pattern) - i.e. the
      traversal logic has moved to attribute access on the new structure.

Exit codes: 0 = all rules pass, 1 = a rule failed, 3 = internal checker error.
"""
import ast
import json
import sys
from pathlib import Path


def main():
    try:
        layers_src = (Path.cwd() / "configmerge" / "layers.py").read_text()
        resolve_src = (Path.cwd() / "configmerge" / "resolve.py").read_text()
        layers_tree = ast.parse(layers_src, filename="layers.py")
        resolve_tree = ast.parse(resolve_src, filename="resolve.py")
    except Exception as exc:  # pragma: no cover - internal checker error path
        print(json.dumps({"error": f"internal checker error: {exc}"}))
        return 3

    rules = {}

    class_defs = [n for n in ast.walk(layers_tree) if isinstance(n, ast.ClassDef)]
    rules["R1_class_defined_in_layers"] = len(class_defs) >= 1

    field_names = {"name", "precedence", "data"}
    offending = []
    for node in ast.walk(resolve_tree):
        if isinstance(node, ast.Subscript):
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value in field_names:
                    offending.append(key.value)
    rules["R2_no_dict_key_access_in_resolve"] = len(offending) == 0

    report = {"rules": rules, "offending_keys": offending, "pass": all(rules.values())}
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
