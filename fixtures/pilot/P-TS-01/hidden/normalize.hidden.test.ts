import { test } from "node:test";
import assert from "node:assert/strict";

test("normalizeField trims and collapses whitespace", () => {
  const mod = require("../src/normalize") as { normalizeField: (v: unknown) => string };
  assert.strictEqual(mod.normalizeField("  Ada   Lovelace \t\n"), "Ada Lovelace");
});

test("normalizeField converts null/undefined to empty string", () => {
  const mod = require("../src/normalize") as { normalizeField: (v: unknown) => string };
  assert.strictEqual(mod.normalizeField(null), "");
  assert.strictEqual(mod.normalizeField(undefined), "");
});

test("normalizeField stringifies non-string values before normalizing", () => {
  const mod = require("../src/normalize") as { normalizeField: (v: unknown) => string };
  assert.strictEqual(mod.normalizeField(42), "42");
  assert.strictEqual(mod.normalizeField(true), "true");
});

test("normalizeField treats an all-whitespace string as empty", () => {
  const mod = require("../src/normalize") as { normalizeField: (v: unknown) => string };
  assert.strictEqual(mod.normalizeField("   \t\n  "), "");
});
