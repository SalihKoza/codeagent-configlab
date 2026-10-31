import { test } from "node:test";
import assert from "node:assert/strict";
import { parseParams } from "../src/index";

test("parses a simple query string into a multimap", () => {
  assert.deepStrictEqual(parseParams("a=1&b=2"), { a: ["1"], b: ["2"] });
});

test("preserves repeated-key values in original order", () => {
  assert.deepStrictEqual(parseParams("a=1&a=2&a=3"), { a: ["1", "2", "3"] });
});

test("decodes percent-encoded keys and values exactly once", () => {
  assert.deepStrictEqual(parseParams("k%20ey=va%2Blue"), { "k ey": ["va+lue"] });
});

test("handles an empty query string", () => {
  assert.deepStrictEqual(parseParams(""), {});
});

test("strips a leading question mark if present", () => {
  assert.deepStrictEqual(parseParams("?a=1"), { a: ["1"] });
});
