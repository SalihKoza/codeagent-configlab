import { test } from "node:test";
import assert from "node:assert/strict";
import { normalize, parseParams, serialize } from "../src/index";

test("normalize sorts keys alphabetically", () => {
  assert.strictEqual(normalize("/api?b=2&a=1"), "/api?a=1&b=2");
});

test("normalize round-trips through parseParams to the same logical multimap", () => {
  const out = normalize("/api?b=2&a=1");
  assert.deepStrictEqual(parseParams(out.split("?")[1]), { a: ["1"], b: ["2"] });
});

test("normalize preserves a single repeated key's values when already sorted", () => {
  assert.strictEqual(normalize("/api?a=1&a=2"), "/api?a=1&a=2");
});

test("a reserved character already percent-encoded round-trips to the same single-encoded form", () => {
  const out = normalize("/api?k=a%2Bb");
  assert.strictEqual(out, "/api?k=a%2Bb");
});

test("serialize preserves given key and value order without sorting", () => {
  assert.strictEqual(serialize({ b: ["2"], a: ["1"] }), "b=2&a=1");
});
