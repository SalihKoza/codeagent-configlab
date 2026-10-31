import { test } from "node:test";
import assert from "node:assert/strict";
import { enqueue, next, size } from "../src/index";

test("next() returns the highest-priority job first", () => {
  enqueue({ id: "ord-a" }, 1);
  enqueue({ id: "ord-b" }, 5);
  enqueue({ id: "ord-c" }, 3);
  assert.strictEqual(next()!.id, "ord-b");
  assert.strictEqual(next()!.id, "ord-c");
  assert.strictEqual(next()!.id, "ord-a");
});

test("equal-priority jobs come out in insertion (FIFO) order", () => {
  enqueue({ id: "ord-t1" }, 2);
  enqueue({ id: "ord-t2" }, 2);
  enqueue({ id: "ord-t3" }, 2);
  assert.strictEqual(next()!.id, "ord-t1");
  assert.strictEqual(next()!.id, "ord-t2");
  assert.strictEqual(next()!.id, "ord-t3");
});

test("size() reflects the number of pending jobs", () => {
  const before = size();
  enqueue({ id: "ord-s1" }, 1);
  enqueue({ id: "ord-s2" }, 1);
  assert.strictEqual(size(), before + 2);
  next();
  assert.strictEqual(size(), before + 1);
  next();
});

test("next() returns undefined when the queue is empty", () => {
  while (size() > 0) next();
  assert.strictEqual(next(), undefined);
});
