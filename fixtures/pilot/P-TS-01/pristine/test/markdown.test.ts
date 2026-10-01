import { test } from "node:test";
import assert from "node:assert/strict";
import { toMarkdown } from "../src/markdown";

test("toMarkdown trims and collapses internal whitespace", () => {
  const out = toMarkdown([{ name: "  Ada   Lovelace ", email: "ada@example.com", notes: null }]);
  assert.strictEqual(out,
    "| name | email | notes |\n| --- | --- | --- |\n| Ada Lovelace | ada@example.com |  |");
});

test("toMarkdown treats undefined the same as null", () => {
  const out = toMarkdown([{ name: "Grace", email: "g@example.com", notes: undefined }]);
  assert.strictEqual(out,
    "| name | email | notes |\n| --- | --- | --- |\n| Grace | g@example.com |  |");
});

test("toMarkdown escapes a pipe character in a field", () => {
  const out = toMarkdown([{ name: "A", email: "a@example.com", notes: "a|b" }]);
  assert.strictEqual(out,
    "| name | email | notes |\n| --- | --- | --- |\n| A | a@example.com | a\\|b |");
});
