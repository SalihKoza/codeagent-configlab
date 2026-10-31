# `qs-normalize`: add `stripParams(url, names)`

## Objective

Add a function that removes specified query parameters from a URL while otherwise normalizing it
exactly as `normalize()` would.

## Current behavior

`normalize()` already performs parse → canonicalize → serialize for an entire query string. There
is currently no way to remove specific parameters as part of that pipeline.

## Required behavior

Add `stripParams(url: string, names: string[]): string`, returning the URL with every query
parameter whose key appears in `names` entirely absent from the output (not merely emptied), and
with every remaining parameter canonicalized identically to what `normalize(url)` would produce
for those remaining parameters. This function must reuse the existing parse/encode logic rather
than reimplementing query-string handling from scratch.

## Preservation requirements

`normalize()`, `parseParams()`, and `serialize()` on their own must be unaffected.

## Scope/integrity rules

Only the repository's global write-scope policy applies (see `CLAUDE.md`): implementation files
are open, files under `test/` are protected, use `scratch_tests/` for your own exploratory tests.

## Validation guidance

Run `npm test`. `test/roundtrip.test.ts` covers the pipeline this function extends.

## Non-requirements

You do not need to support removing a parameter by anything other than exact key-name match (no
pattern/wildcard matching).
