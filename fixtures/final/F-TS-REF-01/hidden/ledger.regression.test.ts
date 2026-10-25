// Regression: public types, exports and error classes stay as they are (statement "Unchanged").
import { test } from "node:test";
import assert from "node:assert/strict";
import * as api from "../src/index";
import {
  createLedger,
  Ledger,
  Outcome,
  ParamError,
  processRequest,
  Request,
  ShortageError,
  UnsupportedOpError,
} from "../src/index";

test("createLedger returns a fresh empty ledger", () => {
  const a: Ledger = createLedger();
  const b = createLedger();
  assert.ok(a.stock instanceof Map);
  assert.ok(Array.isArray(a.journal));
  assert.strictEqual(a.stock.size, 0);
  assert.strictEqual(a.journal.length, 0);
  assert.ok(a !== b && a.stock !== b.stock && a.journal !== b.journal);
});

test("exported functions and parameter counts", () => {
  assert.strictEqual(typeof api.processRequest, "function");
  assert.strictEqual(api.processRequest.length, 2);
  assert.strictEqual(typeof api.createLedger, "function");
  assert.strictEqual(api.createLedger.length, 0);
});

test("exception types keep their fields", () => {
  for (const cls of [UnsupportedOpError, ParamError, ShortageError]) {
    assert.ok(cls.prototype instanceof Error);
  }
  const u = new UnsupportedOpError("zz");
  assert.deepStrictEqual([u.name, u.op, u.message], ["UnsupportedOpError", "zz", "Unsupported operation: zz"]);
  const p = new ParamError("ship", "qty");
  assert.deepStrictEqual([p.name, p.op, p.param, p.message], ["ParamError", "ship", "qty", "ship: invalid qty"]);
  const s = new ShortageError("AB", 3, 1);
  assert.deepStrictEqual([s.name, s.sku, s.requested, s.available, s.message],
    ["ShortageError", "AB", 3, 1, "Insufficient stock for AB: requested 3, available 1"]);
});

test("typed request and outcome usage", () => {
  const ledger = createLedger();
  const request: Request = { op: "receive", params: { sku: "T1", qty: 2 } };
  const outcome: Outcome = processRequest(request, ledger);
  assert.strictEqual(outcome.op, "receive");
  assert.strictEqual(outcome.onHand, 2);
  assert.strictEqual(outcome.lines, undefined);
});

test("journal is append-only across requests", () => {
  const ledger = createLedger();
  processRequest({ op: "receive", params: { sku: "J1", qty: 1 } }, ledger);
  const firstTwo = [...ledger.journal];
  processRequest({ op: "report" }, ledger);
  processRequest({ op: "ship", params: { sku: "J1", qty: 1 } }, ledger);
  assert.deepStrictEqual(ledger.journal.slice(0, 2), firstTwo);
  assert.deepStrictEqual(ledger.journal.slice(2), ["report 1", "ship J1 -1", "depleted J1"]);
});

test("stock holds only positive quantities", () => {
  const ledger = createLedger();
  processRequest({ op: "receive", params: { sku: "V1", qty: 2 } }, ledger);
  processRequest({ op: "receive", params: { sku: "V2", qty: 3 } }, ledger);
  processRequest({ op: "ship", params: { sku: "V1", qty: 2 } }, ledger);
  processRequest({ op: "adjust", params: { sku: "V2", delta: -3, reason: "lost" } }, ledger);
  assert.deepStrictEqual([...ledger.stock.entries()], []);
});

test("count and report outcome shapes", () => {
  const ledger = createLedger();
  processRequest({ op: "receive", params: { sku: "O1", qty: 4 } }, ledger);
  const counted = processRequest({ op: "count", params: { sku: "O1" } }, ledger);
  assert.deepStrictEqual(Object.keys(counted).sort(), ["onHand", "op"]);
  const reported = processRequest({ op: "report" }, ledger);
  assert.deepStrictEqual(Object.keys(reported).sort(), ["lines", "op"]);
  assert.ok(Array.isArray(reported.lines));
});

test("errors thrown by processRequest are the exported classes", () => {
  const ledger = createLedger();
  const errs: unknown[] = [];
  for (const req of [{ op: "nope" }, { op: "count", params: { sku: 1 } }, { op: "ship", params: { sku: "X", qty: 1 } }]) {
    try {
      processRequest(req, ledger);
    } catch (err) {
      errs.push(err);
    }
  }
  assert.ok(errs[0] instanceof UnsupportedOpError);
  assert.ok(errs[1] instanceof ParamError);
  assert.ok(errs[2] instanceof ShortageError);
});
