import { test } from "node:test";
import assert from "node:assert/strict";
import { toJson } from "../src/json";

test("toJson trims and collapses internal whitespace", () => {
  const out = toJson([{ name: "  Ada   Lovelace ", email: "ada@example.com", notes: null }]);
  assert.strictEqual(out, JSON.stringify(
    [{ name: "Ada Lovelace", email: "ada@example.com", notes: "" }], null, 2));
});

test("toJson treats undefined the same as null", () => {
  const out = toJson([{ name: "Grace", email: "g@example.com", notes: undefined }]);
  assert.strictEqual(out, JSON.stringify(
    [{ name: "Grace", email: "g@example.com", notes: "" }], null, 2));
});

test("toJson collapses a tab-and-newline run to one space", () => {
  const out = toJson([{ name: "Ada\t\nLovelace", email: "a@example.com", notes: "" }]);
  assert.strictEqual(out, JSON.stringify(
    [{ name: "Ada Lovelace", email: "a@example.com", notes: "" }], null, 2));
});
