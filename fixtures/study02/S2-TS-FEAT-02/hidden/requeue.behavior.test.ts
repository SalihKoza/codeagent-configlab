import { test } from "node:test";
import assert from "node:assert/strict";
import { enqueue, next, markFailed, requeueFailed, size } from "../src/index";

// Clear any leftover pending/failed state from a previous test in this process before asserting
// counts — requeueFailed()/size() operate on shared module-level state.
function sweep(): void {
  requeueFailed(Number.MAX_SAFE_INTEGER);
  while (size() > 0) next();
}

test("an eligible failed job reappears via next() at its original priority", () => {
  sweep();
  enqueue({ id: "rq-1" }, 7);
  const got = next();
  assert.strictEqual(got!.id, "rq-1");
  markFailed("rq-1");
  assert.strictEqual(size(), 0);
  requeueFailed(3);
  assert.strictEqual(size(), 1);
  assert.strictEqual(next()!.id, "rq-1");
});

test("a failed job at/above maxRetries never reappears via next()", () => {
  sweep();
  enqueue({ id: "rq-2" }, 1);
  next();
  markFailed("rq-2");
  requeueFailed(0); // maxRetries 0 means a job with 0 retries so far is already not below 0
  assert.strictEqual(size(), 0);
});

test("retry count increments by exactly one per requeue, not reset to zero", () => {
  sweep();
  enqueue({ id: "rq-3" }, 2);
  next();
  markFailed("rq-3");
  requeueFailed(2); // retryCount 0 < 2 -> requeued, retryCount becomes 1
  assert.strictEqual(size(), 1);
  next();
  markFailed("rq-3");
  requeueFailed(2); // retryCount 1 < 2 -> requeued, retryCount becomes 2
  assert.strictEqual(size(), 1);
  next();
  markFailed("rq-3");
  requeueFailed(2); // retryCount 2 < 2 is false -> NOT requeued
  assert.strictEqual(size(), 0);
});

test("a job requeued and failed again remains eligible only while still below maxRetries", () => {
  sweep();
  enqueue({ id: "rq-4" }, 5);
  // Cycles 0,1,2 each requeue (retryCount goes 0->1->2->3, each time < maxRetries=3 at the
  // check). Cycle 3 then finds retryCount===3, which is not < 3, so it must NOT be requeued.
  for (let i = 0; i < 4; i++) {
    const got = next();
    assert.ok(got, `expected a job on cycle ${i}`);
    markFailed("rq-4");
    requeueFailed(3);
  }
  assert.strictEqual(size(), 0);
});
