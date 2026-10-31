import { test } from "node:test";
import assert from "node:assert/strict";
import { enqueue, next, markFailed, size } from "../src/index";

test("a job not marked failed is unaffected by markFailed on a different id", () => {
  enqueue({ id: "rt-x1" }, 1);
  const got = next();
  assert.strictEqual(got!.id, "rt-x1");
  markFailed("rt-nonexistent-id");
  assert.strictEqual(size(), 0);
});

test("markFailed on an in-flight job does not re-add it to the pending queue", () => {
  enqueue({ id: "rt-x2" }, 1);
  const before = size();
  const got = next();
  assert.strictEqual(size(), before - 1);
  markFailed(got!.id);
  assert.strictEqual(size(), before - 1);
});
