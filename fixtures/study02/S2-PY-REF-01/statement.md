# `configmerge`: replace the layer-stack representation

## Structural requirement

The layer stack is currently a plain list of plain dicts with no explicit identity beyond list
position. Replace it with an explicit, named structure (your choice of representation — e.g., a
small class or `dataclass`) that gives each layer an explicit identity, while keeping the same
precedence semantics (base, then environment, then per-instance override, applied in that
order).

## Behavioral invariant (must be byte-identical before and after)

Every `resolve()` call (for every key, including dotted paths), `set_override()` call, and
`layers()` call must produce exactly the same result before and after this change, for any
sequence of layer configuration.

## Preservation requirements

Same as the behavioral invariant above — this task adds no new public behavior.

## Scope / integrity rules

Only this repository's global write-scope policy applies.

## Validation guidance

Run `python3 -m unittest discover -s tests -v` from the repository root. The full existing
`tests/test_resolve.py` and `tests/test_layers.py` suites must continue to pass unchanged.

## Non-requirements

You do not need to change the public signatures of `resolve`, `set_override`, or `layers`;
`layers()`'s return value may use your new structure as long as existing callers of `layers()`
continue to get equivalent information in equivalent order.
