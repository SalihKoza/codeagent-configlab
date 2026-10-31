# `throttlekit`: replace the per-client bucket representation

## Structural requirement

Per-client rate-limiter state is currently a raw dict with ad hoc key names. Replace it with an
explicit, named structure (your choice of representation) holding the same fields (token count,
last-refill time, configured rate, configured burst), while keeping `allow`/`configure`/`reset`
behavior identical.

## Behavioral invariant (must be byte-identical before and after)

Every `allow()`, `configure()`, and `reset()` call must produce exactly the same result before
and after this change, including at exact refill boundaries, for any sequence of calls across any
number of clients.

## Preservation requirements

Same as the behavioral invariant above.

## Scope / integrity rules

Only this repository's global write-scope policy applies.

## Validation guidance

Run `python3 -m unittest discover -s tests -v` from the repository root. The full existing
`tests/test_buckets.py` and `tests/test_api.py` suites must continue to pass unchanged.

## Non-requirements

You do not need to change the public signatures of `configure`, `allow`, or `reset`. You do not
need to change how time is read — `clock.py`'s injectable time source must continue to be the
only source of "current time."
