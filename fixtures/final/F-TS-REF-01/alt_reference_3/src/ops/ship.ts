import { ShortageError } from "../errors";
import { readQty, readSku } from "../params";
import type { Ledger, Outcome } from "../types";
import { finish, Params } from "./shared";

export function ship(params: Params, ledger: Ledger): Outcome {
  const sku = readSku("ship", params);
  const qty = readQty("ship", params);
  const available = ledger.stock.get(sku) ?? 0;
  if (qty > available) {
    throw new ShortageError(sku, qty, available);
  }
  ledger.journal.push(`ship ${sku} -${qty}`);
  finish(ledger, sku, available - qty);
  return { op: "ship", onHand: available - qty };
}
