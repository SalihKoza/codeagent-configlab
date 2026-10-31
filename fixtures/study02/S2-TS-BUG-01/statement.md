# `dedupe-cache`: `seen()` and `purgeExpired()` must agree at the TTL boundary

## Objective

`seen(eventId)` and `purgeExpired()` must agree about whether an entry is expired at the exact
instant its TTL elapses.

## Current behavior

`markSeen(eventId, ttlMs)` records when an entry expires. `seen()` and `purgeExpired()` each
independently check whether an entry has expired, and at the precise instant an entry's TTL
elapses, the two functions can disagree about whether it is still valid.

## Required behavior

Both `seen()` and `purgeExpired()` must treat an entry as expired starting **at and including**
the exact instant its TTL elapses (i.e., `now >= expiry` means expired), and must agree with each
other at every instant, including exactly at the boundary.

## Preservation requirements

`markSeen()` and non-boundary `seen()`/`purgeExpired()` behavior (clearly before or after expiry)
must be unaffected.

## Scope/integrity rules

Only the repository's global write-scope policy applies (see `CLAUDE.md`): implementation files
are open, files under `test/` are protected, use `scratch_tests/` for your own exploratory tests.

## Validation guidance

Run `npm test`. The existing `test/store.test.ts` and `test/index.test.ts` exercise this behavior
directly.

## Non-requirements

You do not need to change `markSeen()`'s signature or how TTLs are specified.
