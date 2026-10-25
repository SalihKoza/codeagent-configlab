// Behavior that the refactor must preserve exactly (statement "Behavior"; public entry point only).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  createLedger,
  Ledger,
  Outcome,
  ParamError,
  processRequest,
  ShortageError,
  UnsupportedOpError,
} from "../src/index";

type P = Record<string, unknown>;
// `call` may throw (used where an error is expected); `run` turns an unexpected error into a failed
// assertion, so that a request the contract accepts is reported as an assertion failure.
const call = (ledger: Ledger, op: string, params?: P): Outcome =>
  processRequest(params === undefined ? { op } : { op, params }, ledger);

function run(ledger: Ledger, op: string, params?: P): Outcome {
  try {
    return call(ledger, op, params);
  } catch (err) {
    assert.ok(false, `${op} ${JSON.stringify(params)} unexpectedly threw ${String(err)}`);
    throw err;
  }
}

function thrown(fn: () => unknown): unknown {
  try {
    fn();
  } catch (err) {
    return err;
  }
  assert.ok(false, "expected an error to be thrown");
  return undefined;
}

function assertParamError(err: unknown, op: string, param: string): void {
  assert.ok(err instanceof ParamError, `ParamError expected, got ${String(err)}`);
  const e = err as ParamError;
  assert.strictEqual(e.name, "ParamError");
  assert.strictEqual(e.op, op);
  assert.strictEqual(e.param, param);
  assert.strictEqual(e.message, `${op}: invalid ${param}`);
}

function assertShortage(err: unknown, sku: string, requested: number, available: number): void {
  assert.ok(err instanceof ShortageError, `ShortageError expected, got ${String(err)}`);
  const e = err as ShortageError;
  assert.strictEqual(e.name, "ShortageError");
  assert.strictEqual(e.sku, sku);
  assert.strictEqual(e.requested, requested);
  assert.strictEqual(e.available, available);
  assert.strictEqual(e.message, `Insufficient stock for ${sku}: requested ${requested}, available ${available}`);
}

const snapshot = (ledger: Ledger) => ({ stock: [...ledger.stock.entries()], journal: [...ledger.journal] });

function stocked(entries: [string, number][]): Ledger {
  const ledger = createLedger();
  for (const [sku, qty] of entries) run(ledger, "receive", { sku, qty });
  ledger.journal.length = 0;
  return ledger;
}

test("receive on a new SKU journals new before receive", () => {
  const ledger = createLedger();
  assert.deepStrictEqual(run(ledger, "receive", { sku: "K7", qty: 12 }), { op: "receive", onHand: 12 });
  assert.deepStrictEqual(snapshot(ledger), { stock: [["K7", 12]], journal: ["new K7", "receive K7 +12"] });
});

test("receive on a SKU already on hand adds without a new entry", () => {
  const ledger = stocked([["K7", 3]]);
  assert.deepStrictEqual(run(ledger, "receive", { sku: "K7", qty: 4 }), { op: "receive", onHand: 7 });
  assert.deepStrictEqual(ledger.journal, ["receive K7 +4"]);
});

test("quantity bounds 1 and 10000 are accepted", () => {
  const ledger = createLedger();
  assert.deepStrictEqual(run(ledger, "receive", { sku: "LO", qty: 1 }), { op: "receive", onHand: 1 });
  assert.deepStrictEqual(run(ledger, "receive", { sku: "HI", qty: 10000 }), { op: "receive", onHand: 10000 });
  assert.deepStrictEqual(run(ledger, "ship", { sku: "HI", qty: 10000 }), { op: "ship", onHand: 0 });
  assert.deepStrictEqual(run(ledger, "ship", { sku: "LO", qty: 1 }), { op: "ship", onHand: 0 });
});

test("invalid quantities are rejected for receive and ship", () => {
  const bad: unknown[] = [0, -1, 10001, 1.5, "5", Number.NaN, Number.POSITIVE_INFINITY, null, undefined, true];
  for (const op of ["receive", "ship"]) {
    for (const qty of bad) {
      const ledger = stocked([["Q1", 50]]);
      const params: P = qty === undefined ? { sku: "Q1" } : { sku: "Q1", qty };
      assertParamError(thrown(() => call(ledger, op, params)), op, "qty");
    }
  }
});

test("sku rule boundaries", () => {
  const good = ["A", "A-1", "Z9", "ABCDEFGHIJKLMNOP", "X--"];
  const bad: unknown[] = ["", "a", "1A", "-A", "ABCDEFGHIJKLMNOPQ", "A B", "A_B", "Ab", " A", 5, null, undefined];
  for (const sku of good) {
    const ledger = createLedger();
    assert.deepStrictEqual(run(ledger, "receive", { sku, qty: 2 }), { op: "receive", onHand: 2 });
    assert.deepStrictEqual(run(ledger, "count", { sku }), { op: "count", onHand: 2 });
  }
  for (const sku of bad) {
    for (const [op, extra] of [["receive", { qty: 1 }], ["ship", { qty: 1 }], ["adjust", { delta: 1, reason: "x" }],
      ["count", {}]] as [string, P][]) {
      const params: P = sku === undefined ? { ...extra } : { sku, ...extra };
      assertParamError(thrown(() => call(createLedger(), op, params)), op, "sku");
    }
  }
});

test("parameters are checked in the documented order", () => {
  assertParamError(thrown(() => call(createLedger(), "receive", { sku: "bad", qty: 0 })), "receive", "sku");
  assertParamError(thrown(() => call(createLedger(), "ship", { qty: -2 })), "ship", "sku");
  assertParamError(thrown(() => call(createLedger(), "adjust", { sku: "x", delta: 0, reason: "" })), "adjust", "sku");
  assertParamError(thrown(() => call(createLedger(), "adjust", { sku: "OK", delta: 0, reason: "" })), "adjust", "delta");
  assertParamError(thrown(() => call(createLedger(), "adjust", { sku: "OK", delta: 3, reason: "" })), "adjust", "reason");
  assertParamError(thrown(() => call(createLedger(), "ship", { sku: "OK", qty: 99999 })), "ship", "qty");
});

test("ship down to zero journals depletion and removes the SKU", () => {
  const ledger = stocked([["M4", 6], ["M5", 1]]);
  assert.deepStrictEqual(run(ledger, "ship", { sku: "M4", qty: 6 }), { op: "ship", onHand: 0 });
  assert.deepStrictEqual(snapshot(ledger), { stock: [["M5", 1]], journal: ["ship M4 -6", "depleted M4"] });
  assert.deepStrictEqual(run(ledger, "count", { sku: "M4" }), { op: "count", onHand: 0 });
});

test("ship that leaves stock keeps the SKU", () => {
  const ledger = stocked([["M4", 6]]);
  assert.deepStrictEqual(run(ledger, "ship", { sku: "M4", qty: 2 }), { op: "ship", onHand: 4 });
  assert.deepStrictEqual(snapshot(ledger), { stock: [["M4", 4]], journal: ["ship M4 -2"] });
});

test("ship shortage reports details and changes nothing", () => {
  const ledger = stocked([["P2", 3]]);
  const before = snapshot(ledger);
  assertShortage(thrown(() => call(ledger, "ship", { sku: "P2", qty: 4 })), "P2", 4, 3);
  assertShortage(thrown(() => call(ledger, "ship", { sku: "NONE", qty: 1 })), "NONE", 1, 0);
  assert.deepStrictEqual(snapshot(ledger), before);
});

test("adjust journal format for positive and negative deltas", () => {
  const ledger = stocked([["R1", 10]]);
  assert.deepStrictEqual(run(ledger, "adjust", { sku: "R1", delta: 5, reason: "found" }), { op: "adjust", onHand: 15 });
  assert.deepStrictEqual(run(ledger, "adjust", { sku: "R1", delta: -3, reason: "  broken seal " }), { op: "adjust", onHand: 12 });
  assert.deepStrictEqual(ledger.journal, ["adjust R1 +5 found", "adjust R1 -3 broken seal"]);
});

test("adjust to zero journals depletion after the adjustment", () => {
  const ledger = stocked([["R2", 4]]);
  assert.deepStrictEqual(run(ledger, "adjust", { sku: "R2", delta: -4, reason: "write-off" }), { op: "adjust", onHand: 0 });
  assert.deepStrictEqual(snapshot(ledger), { stock: [], journal: ["adjust R2 -4 write-off", "depleted R2"] });
});

test("adjust below zero is a shortage with requested equal to minus delta", () => {
  const ledger = stocked([["R3", 2]]);
  const before = snapshot(ledger);
  assertShortage(thrown(() => call(ledger, "adjust", { sku: "R3", delta: -5, reason: "count" })), "R3", 5, 2);
  assertShortage(thrown(() => call(ledger, "adjust", { sku: "GONE", delta: -1, reason: "count" })), "GONE", 1, 0);
  assert.deepStrictEqual(snapshot(ledger), before);
});

test("adjust of a SKU not on hand starts from zero without a new entry", () => {
  const ledger = createLedger();
  assert.deepStrictEqual(run(ledger, "adjust", { sku: "S9", delta: 7, reason: "audit" }), { op: "adjust", onHand: 7 });
  assert.deepStrictEqual(snapshot(ledger), { stock: [["S9", 7]], journal: ["adjust S9 +7 audit"] });
});

test("adjust delta bounds", () => {
  const ledger = stocked([["D1", 10000]]);
  assert.deepStrictEqual(run(ledger, "adjust", { sku: "D1", delta: -10000, reason: "r" }), { op: "adjust", onHand: 0 });
  assert.deepStrictEqual(run(ledger, "adjust", { sku: "D1", delta: 10000, reason: "r" }), { op: "adjust", onHand: 10000 });
  for (const delta of [0, 10001, -10001, 2.5, "1", null, Number.NaN] as unknown[]) {
    assertParamError(thrown(() => call(ledger, "adjust", { sku: "D1", delta, reason: "r" })), "adjust", "delta");
  }
  assertParamError(thrown(() => call(ledger, "adjust", { sku: "D1", reason: "r" })), "adjust", "delta");
});

test("adjust reason rules", () => {
  const ledger = stocked([["E1", 100]]);
  const forty = "x".repeat(40);
  run(ledger, "adjust", { sku: "E1", delta: 1, reason: `   ${forty}   ` });
  assert.strictEqual(ledger.journal[ledger.journal.length - 1], `adjust E1 +1 ${forty}`);
  for (const reason of ["", "   ", "\t\n", "y".repeat(41), 7, null] as unknown[]) {
    assertParamError(thrown(() => call(ledger, "adjust", { sku: "E1", delta: 1, reason })), "adjust", "reason");
  }
  assertParamError(thrown(() => call(ledger, "adjust", { sku: "E1", delta: 1 })), "adjust", "reason");
});

test("count returns the quantity and changes nothing", () => {
  const ledger = stocked([["C1", 9]]);
  const before = snapshot(ledger);
  assert.deepStrictEqual(run(ledger, "count", { sku: "C1" }), { op: "count", onHand: 9 });
  assert.deepStrictEqual(run(ledger, "count", { sku: "C2" }), { op: "count", onHand: 0 });
  assert.deepStrictEqual(snapshot(ledger), before);
});

test("report sorts by code unit order and journals the SKU count", () => {
  const ledger = stocked([["Z", 1], ["B", 2], ["A1", 3], ["A-2", 4]]);
  assert.deepStrictEqual(run(ledger, "report"), { op: "report", lines: ["A-2=4", "A1=3", "B=2", "Z=1"] });
  assert.deepStrictEqual(ledger.journal, ["report 4"]);
  const empty = createLedger();
  assert.deepStrictEqual(run(empty, "report", { anything: 1 }), { op: "report", lines: [] });
  assert.deepStrictEqual(empty.journal, ["report 0"]);
});

test("unsupported operations", () => {
  for (const op of ["restock", "", "RECEIVE", "Ship", " count", "report ", "toString", "__proto__",
    "constructor", "hasOwnProperty", "valueOf"]) {
    const ledger = stocked([["U1", 1]]);
    const before = snapshot(ledger);
    const err = thrown(() => call(ledger, op, { sku: "U1", qty: 1 }));
    assert.ok(err instanceof UnsupportedOpError, `UnsupportedOpError expected for ${JSON.stringify(op)}, got ${String(err)}`);
    const e = err as UnsupportedOpError;
    assert.strictEqual(e.name, "UnsupportedOpError");
    assert.strictEqual(e.op, op);
    assert.strictEqual(e.message, `Unsupported operation: ${op}`);
    assert.deepStrictEqual(snapshot(ledger), before);
  }
});

test("an unsupported operation is reported before its parameters are read", () => {
  const err = thrown(() => call(createLedger(), "remove", { sku: 5, qty: "x" }));
  assert.ok(err instanceof UnsupportedOpError);
  assert.ok(!(err instanceof ParamError));
});

test("missing params behave like an empty object", () => {
  assertParamError(thrown(() => call(createLedger(), "receive")), "receive", "sku");
  assertParamError(thrown(() => call(createLedger(), "count")), "count", "sku");
  const ledger = stocked([["N1", 2]]);
  assert.deepStrictEqual(run(ledger, "report"), { op: "report", lines: ["N1=2"] });
});

test("requests and params are not modified", () => {
  const ledger = createLedger();
  const params = Object.freeze({ sku: "F1", qty: 3 });
  const request = Object.freeze({ op: "receive", params });
  processRequest(request, ledger);
  processRequest(Object.freeze({ op: "adjust", params: Object.freeze({ sku: "F1", delta: -1, reason: " r " }) }), ledger);
  assert.deepStrictEqual({ ...params }, { sku: "F1", qty: 3 });
  assert.deepStrictEqual(Object.keys(request).sort(), ["op", "params"]);
  assert.strictEqual(ledger.stock.get("F1"), 2);
});

test("outcomes are new objects", () => {
  const ledger = stocked([["G1", 1]]);
  const first = run(ledger, "report");
  (first.lines as string[]).push("tampered");
  const second = run(ledger, "report");
  assert.deepStrictEqual(second, { op: "report", lines: ["G1=1"] });
  assert.ok(first !== second, "a new outcome object per call");
  assert.ok(run(ledger, "count", { sku: "G1" }) !== run(ledger, "count", { sku: "G1" }));
});

test("repeated calls and independent ledgers", () => {
  const one = createLedger();
  const two = createLedger();
  for (let i = 1; i <= 3; i++) run(one, "receive", { sku: "H1", qty: i });
  assert.deepStrictEqual(snapshot(one), {
    stock: [["H1", 6]], journal: ["new H1", "receive H1 +1", "receive H1 +2", "receive H1 +3"] });
  assert.deepStrictEqual(snapshot(two), { stock: [], journal: [] });
  run(two, "receive", { sku: "H1", qty: 1 });
  assert.strictEqual(one.stock.get("H1"), 6);
});

test("mixed sequence keeps the documented journal order", () => {
  const ledger = createLedger();
  run(ledger, "receive", { sku: "W2", qty: 2 });
  run(ledger, "receive", { sku: "W1", qty: 5 });
  run(ledger, "ship", { sku: "W2", qty: 2 });
  run(ledger, "adjust", { sku: "W1", delta: -1, reason: "dent" });
  thrown(() => call(ledger, "ship", { sku: "W1", qty: 9 }));
  run(ledger, "count", { sku: "W1" });
  run(ledger, "receive", { sku: "W2", qty: 1 });
  assert.deepStrictEqual(run(ledger, "report"), { op: "report", lines: ["W1=4", "W2=1"] });
  assert.deepStrictEqual(ledger.journal, [
    "new W2", "receive W2 +2", "new W1", "receive W1 +5", "ship W2 -2", "depleted W2",
    "adjust W1 -1 dent", "new W2", "receive W2 +1", "report 2"]);
});
