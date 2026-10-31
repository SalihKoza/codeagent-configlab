# `mini-queue`: add `requeueFailed(maxRetries)`

## Objective

Add a function that gives failed jobs another chance, up to a retry limit.

## Current behavior

`markFailed(jobId)` records that a job failed and increments its retry count, but a failed job is
not currently reachable again via `next()` — there is no path back into the pending queue.

## Required behavior

Add `requeueFailed(maxRetries: number): void`. For every job currently tracked as failed whose
retry count is strictly below `maxRetries`: re-insert it into the pending queue at its original
priority (following the queue's existing tie-break-by-insertion-order rule for any ties), and
increment its retry count by one. Jobs whose retry count is already at or above `maxRetries` must
remain excluded from `next()` — they are not requeued.

## Preservation requirements

`enqueue()`, `next()`, `markFailed()`, and `size()` must behave exactly as today for any job that
was never marked failed, and for any job whose retry count is at or above `maxRetries` at the time
`requeueFailed` is called.

## Scope/integrity rules

Only the repository's global write-scope policy applies (see `CLAUDE.md`): implementation files
are open, files under `test/` are protected, use `scratch_tests/` for your own exploratory tests.

## Validation guidance

Run `npm test`. `test/ordering.test.ts` and `test/retries.test.ts` cover the two subsystems this
function bridges.

## Non-requirements

You do not need to support partial/selective requeuing by job ID — this function applies the
same `maxRetries` threshold to every currently-failed job.
