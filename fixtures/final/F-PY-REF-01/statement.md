# svcconfig — split `load_config` into parse, default and validate stages

`svcconfig.load_config(raw)` turns raw key/value settings into an immutable `Config`. Today a
single function body does everything inline: it checks setting names and coerces raw values,
fills in defaults and normalizes values, and validates the result. This is a **refactor**: the
loader must be reorganized into separate stages while its observable behavior stays exactly the
same.

## Behavior to preserve (unchanged)

The current behavior is documented in the `load_config` docstring in `svcconfig/loader.py`, and
parts of it are shown by the public tests. All of it must stay exactly as it is:

- the public API exported by the `svcconfig` package: `load_config`, `Config` and `ConfigError`;
- the signature `load_config(raw)`, with `raw` any mapping of setting names to values;
- the accepted raw forms of every setting, the coercion results, the defaults (including the
  default port that depends on the normalized scheme) and the normalization of every value;
- `ConfigError` (a `ValueError` subclass) as the error type, and the exact error messages listed
  in the docstring;
- which error is raised when several problems exist (the precedence described in the docstring),
  and the order of the rules between settings;
- `Config`: same fields in the same order, immutable, compared by value; `raw` is never modified.

## Required structure

Reorganize the code in the `svcconfig` package into three stages with these exact names:

- `parse_values` — the parse/coerce responsibility (setting names and raw value forms);
- `apply_defaults` — the default/normalize responsibility;
- `validate_values` — the validate responsibility (allowed values, ranges, rules between
  settings).

The names are fixed so the structure can be checked objectively. Each stage may be a module-level
function or a method of a class, in any module of the package. You choose the parameters, return
values, helper functions, classes and file layout.

The structure is checked statically on the source files under `svcconfig/` (nothing is imported or
run for this check). In the rules below:

- a *package function* is a function or method defined at module level or in a class body
  somewhere in `svcconfig/`. A function nested inside another function counts as part of it.
- function A *reaches* function B when A's code calls or mentions B by name, as `name` or
  `something.name`. Mentioning a class reaches its `__init__`, `__post_init__`, `__new__` and
  `__call__`. Mentioning a module-level or class-level variable reaches every package function or
  class named in the expression assigned to that variable, for example a tuple of stages or a dict
  of parser functions. Names are matched by name only.
- the *orchestration code* is `load_config` plus every package function it reaches without going
  through one of the three stages.
- the *region* of a stage is the stage plus every package function it reaches.

The rules:

1. Exactly one function or method is named `parse_values`, exactly one is named
   `apply_defaults`, exactly one is named `validate_values`, and exactly one is named
   `load_config`.
2. `load_config` reaches all three stages. It composes the result through them; it does not
   bypass any of them.
3. The orchestration code contains no parsing, defaulting or validation logic. That means none of
   the following: `if` statements, conditional expressions (`x if c else y`), `and`/`or`,
   comparisons, `raise`, `assert`, `try`, `while`, `match`, comprehensions or generator
   expressions, dict displays, and calls to `int()`, `float()` or `isinstance()`. Calls,
   assignments, `return` and plain `for` loops over the stages are fine.
4. No stage reaches another stage. Only the orchestration code connects them.
5. `int()` and `float()` are called only within the region of `parse_values`. They do not appear in
   the orchestration code or in the regions of the other two stages.
6. Each stage does real work. The region of `parse_values` calls `int()` or `float()`. The region
   of `validate_values` contains a `raise`. The region of `apply_defaults` contains an `if`, a
   conditional expression, `and`/`or`, a `.get(...)` or `.setdefault(...)` call, or a `**`
   dict merge.

## Constraints

- Use only the Python standard library; do not add dependencies.
- Do not change the public tests.

## Running the public tests

    python3 -m unittest tests.test_loader -v
