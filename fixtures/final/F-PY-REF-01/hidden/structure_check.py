"""AST check of the required staged structure of ``svcconfig`` (rules S1-S6 of the task).

Usage: python3 structure_check.py [ROOT]   (ROOT defaults to the current directory)
Analyses every ``ROOT/svcconfig/**/*.py`` with :mod:`ast` only (no import, no execution, no text
matching). Prints one JSON report ``{"ok": bool, "rules": {rule: {"ok", "detail"}}}``.
Exit 0 = every rule holds, 1 = at least one rule fails (a syntax error is a failure),
3 = internal error of this checker.

Definitions (as stated publicly):
- *package function*: a function or method defined at module level or inside the body of a class (at
  any nesting depth) in the package. Functions nested inside functions are part of the
  enclosing function.
- *reaches*: function A reaches B if A's code calls or mentions (``name``, ``obj.name``) B's name;
  mentioning classes reaches their ``__init__``/``__post_init__``/``__new__``/``__call__``; a
  mentioned module-level or class-level name leads to every package function (or class) named in the
  expression assigned to it. Names are resolved by name only (all definitions with that name).
- *orchestration code*: ``load_config`` plus every package function it reaches without passing
  through a stage.
- *region* of a stage: the stage plus every package function it reaches.
"""
import ast
import json
import sys
from pathlib import Path

PACKAGE = "svcconfig"
ENTRY = "load_config"
PARSE, DEFAULTS, VALIDATE = "parse_values", "apply_defaults", "validate_values"
STAGES = (PARSE, DEFAULTS, VALIDATE)
CLASS_HOOKS = ("__init__", "__post_init__", "__new__", "__call__")
COERCION_CALLS = {"int", "float"}
ORCHESTRATION_FORBIDDEN_CALLS = {"int", "float", "isinstance"}
ORCHESTRATION_FORBIDDEN_NODES = tuple(n for n in (
    "If", "IfExp", "BoolOp", "Compare", "Raise", "Assert", "Try", "TryStar", "While", "Match",
    "ListComp", "SetComp", "DictComp", "GeneratorExp", "Dict") if hasattr(ast, n))
RULES = ("S1", "S2", "S3", "S4", "S5", "S6")


def collect(root):
    """Return (functions, classes, tables): functions = list of (id, name, node)."""
    functions, classes, tables = [], {}, {}

    def visit_body(body, where, rel):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fid = f"{rel}:{where}{node.name}@{node.lineno}"
                functions.append((fid, node.name, node))
            elif isinstance(node, ast.ClassDef):
                hooks = [f"{rel}:{where}{node.name}.{n.name}@{n.lineno}" for n in node.body
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                         and n.name in CLASS_HOOKS]
                classes.setdefault(node.name, []).extend(hooks)
                visit_body(node.body, f"{where}{node.name}.", rel)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                mentioned = names_in(node.value)
                for t in targets:
                    for tn in ast.walk(t):
                        if isinstance(tn, ast.Name):
                            tables.setdefault(tn.id, set()).update(mentioned)

    for path in sorted((root / PACKAGE).rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        visit_body(tree.body, "", rel)
    return functions, classes, tables


def names_in(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def build_graph(functions, classes, tables):
    by_name = {}
    for fid, name, _ in functions:
        by_name.setdefault(name, []).append(fid)

    def resolve(name, seen):
        if name in seen:
            return set()
        seen.add(name)
        out = set(by_name.get(name, ()))
        out.update(classes.get(name, ()))
        for inner in tables.get(name, ()):
            out |= resolve(inner, seen)
        return out

    edges = {}
    for fid, _, node in functions:
        targets = set()
        for name in names_in(node):
            targets |= resolve(name, set())
        edges[fid] = targets
    return by_name, edges


def reach(start, edges, stop):
    """Functions reached from ``start`` (inclusive); nodes in ``stop`` are recorded, not expanded."""
    seen, todo = {start}, [start]
    while todo:
        cur = todo.pop()
        if cur in stop and cur != start:
            continue
        for nxt in edges.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def calls_to(node, names):
    return [(n.func.id, n.lineno) for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in names]


def evaluate(root):
    rules = {r: {"ok": False, "detail": []} for r in RULES}
    try:
        functions, classes, tables = collect(root)
    except SyntaxError as exc:
        for r in RULES:
            rules[r]["detail"].append(f"not evaluated: syntax error {exc.filename}:{exc.lineno}")
        return rules
    nodes = {fid: node for fid, _, node in functions}
    by_name, edges = build_graph(functions, classes, tables)

    # S1: exactly one definition of each stage and of the loader
    counts = {n: len(by_name.get(n, ())) for n in (ENTRY, *STAGES)}
    rules["S1"]["ok"] = all(c == 1 for c in counts.values())
    rules["S1"]["detail"].append(f"definition counts {counts}")
    if counts[ENTRY] != 1:
        for r in RULES[1:]:
            rules[r]["detail"].append(f"not evaluated: {ENTRY} defined {counts[ENTRY]} times")
        return rules
    entry = by_name[ENTRY][0]
    stage_ids = {fid: name for name in STAGES for fid in by_name.get(name, ())}

    # S2: the loader reaches every stage (through orchestration code only)
    orchestration = reach(entry, edges, set(stage_ids))
    reached = sorted({stage_ids[f] for f in orchestration if f in stage_ids})
    rules["S2"]["ok"] = set(reached) == set(STAGES)
    rules["S2"]["detail"].append(f"stages reached from {ENTRY}: {reached}")

    # S3: orchestration code holds no parsing / defaulting / validation logic
    offenders = []
    for fid in sorted(orchestration - set(stage_ids)):
        node = nodes[fid]
        for n in ast.walk(node):
            if type(n).__name__ in ORCHESTRATION_FORBIDDEN_NODES:
                offenders.append(f"{fid}: {type(n).__name__} at line {n.lineno}")
        for name, line in calls_to(node, ORCHESTRATION_FORBIDDEN_CALLS):
            offenders.append(f"{fid}: call {name}() at line {line}")
    rules["S3"]["ok"] = not offenders
    rules["S3"]["detail"].append(
        f"orchestration functions: {sorted(orchestration - set(stage_ids))}")
    rules["S3"]["detail"].extend(offenders[:40])

    # S4: no stage reaches another stage; regions per stage
    regions, crossings = {}, []
    for fid, name in stage_ids.items():
        region = reach(fid, edges, set(stage_ids))
        others = sorted({stage_ids[f] for f in region if f in stage_ids and f != fid})
        if others:
            crossings.append(f"{name} reaches {others}")
        regions.setdefault(name, set()).update(region - (set(stage_ids) - {fid}))
    rules["S4"]["ok"] = bool(stage_ids) and not crossings
    rules["S4"]["detail"].extend(crossings or (["no stage reaches another stage"] if stage_ids
                                               else ["no stage is defined"]))
    for name in STAGES:
        regions.setdefault(name, set())

    # S5: int()/float() only in the parse stage's region
    misplaced = []
    outside = (orchestration - set(stage_ids)) | regions[DEFAULTS] | regions[VALIDATE]
    for fid in sorted(outside):
        for name, line in calls_to(nodes[fid], COERCION_CALLS):
            misplaced.append(f"{fid}: {name}() at line {line}")
    rules["S5"]["ok"] = bool(regions[PARSE]) and not misplaced
    rules["S5"]["detail"].extend(misplaced[:40] or ["int()/float() only in the parse region"])

    # S6: each stage region carries its responsibility
    def any_node(region, pred):
        return any(pred(n) for fid in region for n in ast.walk(nodes[fid]))

    parse_ok = any(calls_to(nodes[f], COERCION_CALLS) for f in regions[PARSE])
    validate_ok = any_node(regions[VALIDATE], lambda n: isinstance(n, ast.Raise))
    defaults_ok = any_node(regions[DEFAULTS], lambda n: (
        isinstance(n, (ast.If, ast.IfExp, ast.BoolOp))
        or (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("get", "setdefault"))
        or (isinstance(n, ast.Dict) and None in n.keys)))
    rules["S6"]["ok"] = parse_ok and validate_ok and defaults_ok
    rules["S6"]["detail"].append(f"{PARSE} coerces: {parse_ok}; {VALIDATE} raises: {validate_ok}; "
                                 f"{DEFAULTS} defaults: {defaults_ok}")
    return rules


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    try:
        rules = evaluate(root)
    except Exception as exc:  # a defect of this checker, never a task verdict
        print(json.dumps({"internal_error": f"{type(exc).__name__}: {exc}"}))
        return 3
    ok = all(r["ok"] for r in rules.values())
    print(json.dumps({"ok": ok, "rules": rules}, indent=1, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
