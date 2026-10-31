import { test } from "node:test";
import assert from "node:assert/strict";
import { normalize, parseParams } from "../src/index";

test("repeated key values not already sorted preserve original relative order after normalize", () => {
  // Keys get canonicalized (a before b); the repeated key "a"'s own two values must keep their
  // original relative order (2 then 1), not be resorted to (1 then 2).
  const out = normalize("/api?b=2&a=2&a=1");
  assert.strictEqual(out, "/api?a=2&a=1&b=2");
});

test("a different repeated key with unsorted values also preserves order", () => {
  const out = normalize("/api?z=9&z=3&z=3&a=1");
  assert.strictEqual(out, "/api?a=1&z=9&z=3&z=3");
});

test("normalize output is re-parseable into the same logical multimap", () => {
  const out = normalize("/api?b=2&a=2&a=1");
  assert.deepStrictEqual(parseParams(out.split("?")[1]), { a: ["2", "1"], b: ["2"] });
});
