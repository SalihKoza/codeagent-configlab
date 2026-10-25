import { test } from "node:test";
import assert from "node:assert/strict";
import { createLedger, ParamError, processRequest, ShortageError, UnsupportedOpError } from "../src/index";

function thrown(fn: () => unknown): unknown {
  try {
    fn();
  } catch (err) {
    return err;
  }
  assert.ok(false, "expected an error to be thrown");
  return undefined;
}

test("receive adds stock and journals a new SKU first", () => {
  const ledger = createLedger();
  assert.deepStrictEqual(processRequest({ op: "receive", params: { sku: "BOLT-8", qty: 5 } }, ledger),
    { op: "receive", onHand: 5 });
  assert.deepStrictEqual(ledger.journal, ["new BOLT-8", "receive BOLT-8 +5"]);
  assert.strictEqual(ledger.stock.get("BOLT-8"), 5);
});

test("ship removes stock and journals depletion", () => {
  const ledger = createLedger();
  processRequest({ op: "receive", params: { sku: "NUT", qty: 3 } }, ledger);
  assert.deepStrictEqual(processRequest({ op: "ship", params: { sku: "NUT", qty: 3 } }, ledger),
    { op: "ship", onHand: 0 });
  assert.deepStrictEqual(ledger.journal.slice(2), ["ship NUT -3", "depleted NUT"]);
  assert.strictEqual(ledger.stock.has("NUT"), false);
});

test("ship beyond stock raises ShortageError", () => {
  const ledger = createLedger();
  processRequest({ op: "receive", params: { sku: "NUT", qty: 2 } }, ledger);
  const err = thrown(() => processRequest({ op: "ship", params: { sku: "NUT", qty: 4 } }, ledger));
  assert.ok(err instanceof ShortageError);
  assert.strictEqual((err as ShortageError).message, "Insufficient stock for NUT: requested 4, available 2");
});

test("adjust applies a signed correction with a reason", () => {
  const ledger = createLedger();
  processRequest({ op: "receive", params: { sku: "WASHER", qty: 10 } }, ledger);
  const out = processRequest({ op: "adjust", params: { sku: "WASHER", delta: -4, reason: " damaged " } }, ledger);
  assert.deepStrictEqual(out, { op: "adjust", onHand: 6 });
  assert.strictEqual(ledger.journal[ledger.journal.length - 1], "adjust WASHER -4 damaged");
});

test("count reports the on-hand quantity without journaling", () => {
  const ledger = createLedger();
  assert.deepStrictEqual(processRequest({ op: "count", params: { sku: "GEAR" } }, ledger),
    { op: "count", onHand: 0 });
  assert.deepStrictEqual(ledger.journal, []);
});

test("report lists SKUs in order", () => {
  const ledger = createLedger();
  processRequest({ op: "receive", params: { sku: "Z9", qty: 1 } }, ledger);
  processRequest({ op: "receive", params: { sku: "A1", qty: 2 } }, ledger);
  assert.deepStrictEqual(processRequest({ op: "report" }, ledger), { op: "report", lines: ["A1=2", "Z9=1"] });
  assert.strictEqual(ledger.journal[ledger.journal.length - 1], "report 2");
});

test("invalid parameters raise ParamError", () => {
  const err = thrown(() => processRequest({ op: "receive", params: { sku: "bolt", qty: 1 } }, createLedger()));
  assert.ok(err instanceof ParamError);
  assert.strictEqual((err as ParamError).message, "receive: invalid sku");
});

test("an unsupported operation raises UnsupportedOpError", () => {
  const err = thrown(() => processRequest({ op: "restock" }, createLedger()));
  assert.ok(err instanceof UnsupportedOpError);
  assert.strictEqual((err as UnsupportedOpError).message, "Unsupported operation: restock");
});
