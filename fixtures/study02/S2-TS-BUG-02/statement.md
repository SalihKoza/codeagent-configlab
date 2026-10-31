# `qs-normalize`: fix a `normalize()` correctness defect

## Objective

`normalize(url)` must not corrupt a query string's repeated-key ordering or character encoding.

## Current behavior

`normalize()` parses a URL's query string, canonicalizes it, and re-serializes it. For most
inputs this round-trips correctly, but for inputs involving repeated query keys whose values are
not already in sorted order, the output does not faithfully preserve the input's intended
parameter ordering.

## Required behavior

`normalize(url)` must: (a) sort only top-level parameter keys for canonical ordering, never
reordering the list of values belonging to one repeated key; (b) continue to apply
percent-encoding to each logical character exactly once, so that a value already containing a
percent-encoded reserved character round-trips to the same single-encoded form.

## Preservation requirements

`parseParams()` and `serialize()` must behave as they do today for already-well-formed inputs (no
repeated keys with out-of-order values).

## Scope/integrity rules

Only the repository's global write-scope policy applies (see `CLAUDE.md`): implementation files
are open, files under `test/` are protected, use `scratch_tests/` for your own exploratory tests.

## Validation guidance

Run `npm test`. `test/parse.test.ts` and `test/roundtrip.test.ts` cover this behavior directly.

## Non-requirements

You do not need to change `parseParams()`'s or `serialize()`'s public signatures.
