import { test } from "node:test";
import assert from "node:assert/strict";
import { stripParams } from "../src/index";

test("removes a single-occurrence named key entirely", () => {
  assert.strictEqual(stripParams("/api?a=1&b=2", ["b"]), "/api?a=1");
});

test("removes every occurrence of a repeated named key", () => {
  assert.strictEqual(stripParams("/api?a=1&b=2&a=3", ["a"]), "/api?b=2");
});

test("a name not present in the URL is a no-op", () => {
  assert.strictEqual(stripParams("/api?a=1&b=2", ["z"]), "/api?a=1&b=2");
});

test("a stripped name that is a substring of another parameter name does not affect the other", () => {
  assert.strictEqual(stripParams("/api?a=1&ab=2", ["a"]), "/api?ab=2");
});

test("remaining parameters are canonicalized identically to normalize's own output", () => {
  assert.strictEqual(stripParams("/api?b=2&a=1&c=3", ["c"]), "/api?a=1&b=2");
});
