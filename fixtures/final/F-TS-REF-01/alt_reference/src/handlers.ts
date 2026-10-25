import { ShortageError } from "./errors";
import { readDelta, readQty, readReason, readSku } from "./params";
import { onHandOf, record, settle } from "./stockops";
import type { Ledger, Outcome } from "./types";

type Params = Readonly<Record<string, unknown>>;
export type OpHandler = (params: Params, ledger: Ledger) => Outcome;

/** Operation identifier -> handler, filled by `register` below. No prototype, so only own keys exist. */
export const opHandlers: Record<string, OpHandler> = Object.create(null);

function register(op: string, handler: OpHandler): void {
  opHandlers[op] = handler;
}

register("receive", (params, ledger) => {
  const sku = readSku("receive", params);
  const qty = readQty("receive", params);
  const isNew = !ledger.stock.has(sku);
  if (isNew) {
    record(ledger, `new ${sku}`);
  }
  const onHand = onHandOf(ledger, sku) + qty;
  ledger.stock.set(sku, onHand);
  record(ledger, `receive ${sku} +${qty}`);
  return { op: "receive", onHand };
});

register("ship", (params, ledger) => {
  const sku = readSku("ship", params);
  const qty = readQty("ship", params);
  const available = onHandOf(ledger, sku);
  if (available < qty) {
    throw new ShortageError(sku, qty, available);
  }
  record(ledger, `ship ${sku} -${qty}`);
  settle(ledger, sku, available - qty);
  return { op: "ship", onHand: available - qty };
});

register("adjust", (params, ledger) => {
  const sku = readSku("adjust", params);
  const delta = readDelta("adjust", params);
  const reason = readReason("adjust", params);
  const available = onHandOf(ledger, sku);
  if (available + delta < 0) {
    throw new ShortageError(sku, -delta, available);
  }
  const signed = delta > 0 ? `+${delta}` : String(delta);
  record(ledger, `adjust ${sku} ${signed} ${reason}`);
  settle(ledger, sku, available + delta);
  return { op: "adjust", onHand: available + delta };
});

register("count", (params, ledger) => ({ op: "count", onHand: onHandOf(ledger, readSku("count", params)) }));

register("report", (_params, ledger) => {
  const lines = [...ledger.stock.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([sku, qty]) => `${sku}=${qty}`);
  record(ledger, `report ${lines.length}`);
  return { op: "report", lines };
});
