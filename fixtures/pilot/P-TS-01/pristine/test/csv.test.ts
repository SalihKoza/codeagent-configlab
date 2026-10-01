import { test } from "node:test";
import assert from "node:assert/strict";
import { toCsv } from "../src/csv";

test("toCsv trims and collapses internal whitespace", () => {
  const out = toCsv([{ name: "  Ada   Lovelace ", email: "ada@example.com", notes: null }]);
  assert.strictEqual(out, "name,email,notes\nAda Lovelace,ada@example.com,");
});

test("toCsv treats undefined the same as null", () => {
  const out = toCsv([{ name: "Grace", email: "g@example.com", notes: undefined }]);
  assert.strictEqual(out, "name,email,notes\nGrace,g@example.com,");
});

test("toCsv quotes a value containing a comma", () => {
  const out = toCsv([{ name: "Doe, John", email: "j@example.com", notes: "" }]);
  assert.strictEqual(out, 'name,email,notes\n"Doe, John",j@example.com,');
});

test("toCsv collapses a tab-and-newline run to one space", () => {
  const out = toCsv([{ name: "Ada\t\nLovelace", email: "a@example.com", notes: "" }]);
  assert.strictEqual(out, "name,email,notes\nAda Lovelace,a@example.com,");
});
