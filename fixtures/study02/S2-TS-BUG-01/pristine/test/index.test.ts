import { test } from "node:test";
import assert from "node:assert/strict";
import { markSeen, seen, purgeExpired } from "../src/index";
import { setClock } from "../src/clock";

function sweep(): void {
  setClock(() => Number.MAX_SAFE_INTEGER);
  purgeExpired();
}

test("markSeen then seen immediately is true", () => {
  sweep();
  setClock(() => 0);
  markSeen("rt-a", 10000);
  assert.strictEqual(seen("rt-a"), true);
});

test("purgeExpired returns 0 when nothing is expired", () => {
  sweep();
  setClock(() => 0);
  markSeen("rt-b", 10000);
  assert.strictEqual(purgeExpired(), 0);
});
