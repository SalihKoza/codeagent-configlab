# `mini-queue`: extract pending-job ordering into its own abstraction

## Structural requirement

Pending-job ordering is currently maintained by re-sorting the entire pending collection on every
`enqueue()` call. Extract this into a dedicated, encapsulated ordering abstraction (your choice of
internal representation) that `enqueue()`, `next()`, and `size()` use, instead of manipulating a
raw array directly.

## Behavioral invariant (must be byte-identical before and after)

For any sequence of `enqueue()`/`next()`/`size()` calls, including jobs enqueued with equal
priority (where the existing insertion-order tie-break must still apply), results must be
identical before and after this change.

## Preservation requirements

Same as the behavioral invariant above — this task adds no new public behavior.

## Scope/integrity rules

Only the repository's global write-scope policy applies (see `CLAUDE.md`): implementation files
are open, files under `test/` are protected, use `scratch_tests/` for your own exploratory tests.

## Validation guidance

Run `npm test`. The full existing `test/ordering.test.ts` and `test/retries.test.ts` suites must
continue to pass unchanged.

## Non-requirements

You do not need to change the public signatures of `enqueue`, `next`, or `size`. You do not need
to change how retries are tracked.
