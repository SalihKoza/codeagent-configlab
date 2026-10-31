import { test } from "node:test";
import assert from "node:assert/strict";
import { markSeen, seen, purgeExpired } from "../src/index";
import { setClock } from "../src/clock";

function sweep(): void {
  setClock(() => Number.MAX_SAFE_INTEGER);
  purgeExpired();
}

test("seen() is false for an unknown event id", () => {
  sweep();
  setClock(() => 0);
  assert.strictEqual(seen("rt-never-seen"), false);
});

test("seen() is true strictly before expiry", () => {
  sweep();
  let t = 0;
  setClock(() => t);
  markSeen("rt-e1", 1000);
  t = 500;
  assert.strictEqual(seen("rt-e1"), true);
});

test("seen() is false strictly after expiry", () => {
  sweep();
  let t = 0;
  setClock(() => t);
  markSeen("rt-e2", 1000);
  t = 2000;
  assert.strictEqual(seen("rt-e2"), false);
});

test("purgeExpired() removes a strictly-expired entry and returns the count", () => {
  sweep();
  let t = 0;
  setClock(() => t);
  markSeen("rt-e3", 1000);
  t = 5000;
  assert.strictEqual(purgeExpired(), 1);
  assert.strictEqual(seen("rt-e3"), false);
});

test("purgeExpired() leaves a strictly-valid entry in place", () => {
  sweep();
  let t = 0;
  setClock(() => t);
  markSeen("rt-e4", 1000);
  t = 100;
  assert.strictEqual(purgeExpired(), 0);
});

test("at the exact TTL boundary, seen() reports not-seen and purgeExpired() removes it", () => {
  sweep();
  let t = 0;
  setClock(() => t);
  markSeen("rt-boundary", 1000);
  t = 1000;
  assert.strictEqual(seen("rt-boundary"), false);
  assert.strictEqual(purgeExpired(), 1);
});
