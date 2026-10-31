# `dedupe-cache`: consolidate the duplicated expiry-check logic

## Structural requirement

The logic that determines whether an entry has expired is currently implemented independently
inside both `seen()` and `purgeExpired()`. Extract it into one shared helper that both functions
call, eliminating the duplication, while keeping the expiry convention (an entry is expired
starting at and including its exact expiry instant) unchanged.

## Behavioral invariant (must be byte-identical before and after)

Every `markSeen()`, `seen()`, and `purgeExpired()` call must produce exactly the same result
before and after this change, including at exact TTL boundaries, for any sequence of calls across
any number of event IDs.

## Preservation requirements

Same as the behavioral invariant above — this task adds no new public behavior.

## Scope/integrity rules

Only the repository's global write-scope policy applies (see `CLAUDE.md`): implementation files
are open, files under `test/` are protected, use `scratch_tests/` for your own exploratory tests.

## Validation guidance

Run `npm test`. The full existing `test/store.test.ts` and `test/index.test.ts` suites must
continue to pass unchanged.

## Non-requirements

You do not need to change the public signatures of `markSeen`, `seen`, or `purgeExpired`. You do
not need to change how time is read — `clock.ts`'s injectable time source must continue to be the
only source of "current time."
