import { readQty, readSku } from "../params";
import type { Ledger, Outcome } from "../types";
import type { Params } from "./shared";

export function receive(params: Params, ledger: Ledger): Outcome {
  const sku = readSku("receive", params);
  const qty = readQty("receive", params);
  const known = ledger.stock.has(sku);
  const onHand = (ledger.stock.get(sku) ?? 0) + qty;
  if (!known) {
    ledger.journal.push(`new ${sku}`);
  }
  ledger.stock.set(sku, onHand);
  ledger.journal.push(`receive ${sku} +${qty}`);
  return { op: "receive", onHand };
}
