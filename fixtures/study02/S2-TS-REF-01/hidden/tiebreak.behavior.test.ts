import { test } from "node:test";
import assert from "node:assert/strict";
import { enqueue, next, size } from "../src/index";

function drain(): void {
  while (size() > 0) next();
}

test("five equal-priority jobs come out in exact insertion (FIFO) order", () => {
  drain();
  const ids = ["tb-1", "tb-2", "tb-3", "tb-4", "tb-5"];
  for (const id of ids) enqueue({ id }, 4);
  const out: string[] = [];
  for (let i = 0; i < ids.length; i++) out.push(next()!.id);
  assert.deepStrictEqual(out, ids);
});

test("FIFO tie-break holds even when interleaved with higher-priority jobs", () => {
  drain();
  enqueue({ id: "tb-a" }, 2);
  enqueue({ id: "tb-b" }, 2);
  enqueue({ id: "tb-hi" }, 9);
  enqueue({ id: "tb-c" }, 2);
  assert.strictEqual(next()!.id, "tb-hi");
  assert.strictEqual(next()!.id, "tb-a");
  assert.strictEqual(next()!.id, "tb-b");
  assert.strictEqual(next()!.id, "tb-c");
});
