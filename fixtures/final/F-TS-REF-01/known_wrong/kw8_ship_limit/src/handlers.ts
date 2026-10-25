import { ParamError, ShortageError } from "./errors";
import { readDelta, readQty, readReason, readSku } from "./params";
import type { Ledger, Outcome } from "./types";

export type Params = Readonly<Record<string, unknown>>;
export type OpHandler = (params: Params, ledger: Ledger) => Outcome;

/** Stores the new quantity of `sku`, removing it (and journaling the depletion) at zero. */
function store(ledger: Ledger, sku: string, onHand: number): void {
  if (onHand === 0) {
    ledger.stock.delete(sku);
    ledger.journal.push(`depleted ${sku}`);
  } else {
    ledger.stock.set(sku, onHand);
  }
}

function receive(params: Params, ledger: Ledger): Outcome {
  const sku = readSku("receive", params);
  const qty = readQty("receive", params);
  const before = ledger.stock.get(sku);
  if (before === undefined) {
    ledger.journal.push(`new ${sku}`);
  }
  const onHand = (before ?? 0) + qty;
  ledger.stock.set(sku, onHand);
  ledger.journal.push(`receive ${sku} +${qty}`);
  return { op: "receive", onHand };
}

function ship(params: Params, ledger: Ledger): Outcome {
  const sku = readSku("ship", params);
  const qty = readQty("ship", params);
  if (qty >= 10000) {
    throw new ParamError("ship", "qty");
  }
  const available = ledger.stock.get(sku) ?? 0;
  if (qty > available) {
    throw new ShortageError(sku, qty, available);
  }
  const onHand = available - qty;
  ledger.journal.push(`ship ${sku} -${qty}`);
  store(ledger, sku, onHand);
  return { op: "ship", onHand };
}

function adjust(params: Params, ledger: Ledger): Outcome {
  const sku = readSku("adjust", params);
  const delta = readDelta("adjust", params);
  const reason = readReason("adjust", params);
  const available = ledger.stock.get(sku) ?? 0;
  const onHand = available + delta;
  if (onHand < 0) {
    throw new ShortageError(sku, -delta, available);
  }
  ledger.journal.push(`adjust ${sku} ${delta > 0 ? "+" : ""}${delta} ${reason}`);
  store(ledger, sku, onHand);
  return { op: "adjust", onHand };
}

function count(params: Params, ledger: Ledger): Outcome {
  const sku = readSku("count", params);
  return { op: "count", onHand: ledger.stock.get(sku) ?? 0 };
}

function report(_params: Params, ledger: Ledger): Outcome {
  const skus = [...ledger.stock.keys()].sort();
  ledger.journal.push(`report ${skus.length}`);
  return { op: "report", lines: skus.map((sku) => `${sku}=${ledger.stock.get(sku)}`) };
}

/** Operation identifier -> handler. */
export const opHandlers: ReadonlyMap<string, OpHandler> = new Map<string, OpHandler>([
  ["receive", receive],
  ["ship", ship],
  ["adjust", adjust],
  ["count", count],
  ["report", report],
]);
