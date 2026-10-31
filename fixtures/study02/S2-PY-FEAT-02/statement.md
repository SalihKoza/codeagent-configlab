# `configmerge`: add a `list_strategy` option to `resolve`

## Objective

Allow the caller to choose, per call, whether list-valued keys are resolved by replacement
(today's only behavior) or by appending every layer's list together.

## Current behavior

`resolve(key)` walks configuration layers from most- to least-specific and returns the first
value found for `key`, for any value type including lists — the most-specific layer's list wins
outright, and less-specific layers' values for that key are never consulted.

## Required behavior

Add an optional parameter: `resolve(key, list_strategy="replace")`.
- `list_strategy="replace"` (the default, used when the parameter is omitted): behavior is
  unchanged from today, for every key type.
- `list_strategy="append"`, applied only to a key whose resolved value is a list: concatenate the
  list value from every layer that defines that key, ordered least-specific first, most-specific
  last (i.e., the order layers would be applied in, not the order they're searched in).
- `list_strategy="append"` applied to a key whose value is not a list: behaves exactly as
  `"replace"` would for that key.

## Preservation requirements

`resolve(key)` called with no `list_strategy` argument, `set_override()`, and `layers()` must all
be unchanged.

## Scope / integrity rules

Only this repository's global write-scope policy applies.

## Validation guidance

Run `python3 -m unittest discover -s tests -v` from the repository root. `tests/test_resolve.py`
covers resolution and merge-strategy behavior directly.

## Non-requirements

You do not need to support any `list_strategy` value other than `"replace"` and `"append"`; an
unrecognized value's behavior is not specified by this task and will not be tested.
