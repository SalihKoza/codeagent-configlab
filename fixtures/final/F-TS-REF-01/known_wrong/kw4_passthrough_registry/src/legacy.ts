import { ShortageError, UnsupportedOpError } from "./errors";
import { readDelta, readQty, readReason, readSku } from "./params";
import type { Ledger, Outcome, Request } from "./types";

/**
 * Former dispatcher, kept for compatibility. Applies one request to `ledger`.
 *
 * Supported operations (`request.op`):
 * - `receive` {sku, qty}: adds `qty`. Journal: `new <sku>` if the SKU was not on hand, then
 *   `receive <sku> +<qty>`. Outcome `{op, onHand}`.
 * - `ship` {sku, qty}: removes `qty` (ShortageError if fewer are on hand). Journal:
 *   `ship <sku> -<qty>`, then `depleted <sku>` if nothing is left (the SKU is then removed).
 *   Outcome `{op, onHand}`.
 * - `adjust` {sku, delta, reason}: adds `delta` (ShortageError with requested = -delta if the
 *   result would be negative). Journal: `adjust <sku> +<delta>|-<n> <reason>`, then
 *   `depleted <sku>` if nothing is left. Outcome `{op, onHand}`.
 * - `count` {sku}: no change, no journal entry. Outcome `{op, onHand}` (0 if not on hand).
 * - `report` {}: journal `report <number of SKUs>`. Outcome `{op, lines}` with one `<sku>=<qty>`
 *   line per SKU, sorted by SKU.
 *
 * Any other `op` throws UnsupportedOpError before parameters are read. Parameters are checked in
 * the order sku, qty/delta, reason (ParamError). A request that throws changes nothing. The
 * request is never modified.
 */
export function dispatchLegacy(request: Request, ledger: Ledger): Outcome {
  const params = request.params ?? {};
  switch (request.op) {
    case "receive": {
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
    case "ship": {
      const sku = readSku("ship", params);
      const qty = readQty("ship", params);
      const available = ledger.stock.get(sku) ?? 0;
      if (qty > available) {
        throw new ShortageError(sku, qty, available);
      }
      const onHand = available - qty;
      ledger.journal.push(`ship ${sku} -${qty}`);
      if (onHand === 0) {
        ledger.stock.delete(sku);
        ledger.journal.push(`depleted ${sku}`);
      } else {
        ledger.stock.set(sku, onHand);
      }
      return { op: "ship", onHand };
    }
    case "adjust": {
      const sku = readSku("adjust", params);
      const delta = readDelta("adjust", params);
      const reason = readReason("adjust", params);
      const available = ledger.stock.get(sku) ?? 0;
      const onHand = available + delta;
      if (onHand < 0) {
        throw new ShortageError(sku, -delta, available);
      }
      ledger.journal.push(`adjust ${sku} ${delta > 0 ? "+" : ""}${delta} ${reason}`);
      if (onHand === 0) {
        ledger.stock.delete(sku);
        ledger.journal.push(`depleted ${sku}`);
      } else {
        ledger.stock.set(sku, onHand);
      }
      return { op: "adjust", onHand };
    }
    case "count": {
      const sku = readSku("count", params);
      return { op: "count", onHand: ledger.stock.get(sku) ?? 0 };
    }
    case "report": {
      const skus = [...ledger.stock.keys()].sort();
      ledger.journal.push(`report ${skus.length}`);
      return { op: "report", lines: skus.map((sku) => `${sku}=${ledger.stock.get(sku)}`) };
    }
    default:
      throw new UnsupportedOpError(request.op);
  }
}
