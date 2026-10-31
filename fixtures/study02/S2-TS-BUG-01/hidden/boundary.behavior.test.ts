import { test } from "node:test";
import assert from "node:assert/strict";
import { markSeen, seen, purgeExpired } from "../src/index";
import { setClock } from "../src/clock";

function sweep(): void {
  setClock(() => Number.MAX_SAFE_INTEGER);
  purgeExpired();
}

test("at the exact TTL boundary, seen() reports not-seen", () => {
  sweep();
  let t = 0;
  setClock(() => t);
  markSeen("boundary-1", 1000);
  t = 1000; // now === expiry exactly
  assert.strictEqual(seen("boundary-1"), false);
});

test("at the exact TTL boundary, purgeExpired() removes the entry", () => {
  sweep();
  let t = 0;
  setClock(() => t);
  markSeen("boundary-2", 1000);
  t = 1000;
  assert.strictEqual(purgeExpired(), 1);
});

test("at a second, different exact TTL boundary, both functions still agree", () => {
  sweep();
  let t = 0;
  setClock(() => t);
  markSeen("boundary-3", 2500);
  t = 2500;
  assert.strictEqual(seen("boundary-3"), false);
  assert.strictEqual(purgeExpired(), 1);
});

test("strictly before expiry, both seen() and purgeExpired() agree it is valid", () => {
  sweep();
  let t = 0;
  setClock(() => t);
  markSeen("boundary-4", 1000);
  t = 999;
  assert.strictEqual(seen("boundary-4"), true);
  assert.strictEqual(purgeExpired(), 0);
});

test("strictly after expiry, both seen() and purgeExpired() agree it is expired", () => {
  sweep();
  let t = 0;
  setClock(() => t);
  markSeen("boundary-5", 1000);
  t = 1001;
  assert.strictEqual(seen("boundary-5"), false);
  assert.strictEqual(purgeExpired(), 1);
});
