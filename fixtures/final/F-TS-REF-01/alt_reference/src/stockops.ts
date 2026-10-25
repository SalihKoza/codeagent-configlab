import type { Ledger } from "./types";

export function onHandOf(ledger: Ledger, sku: string): number {
  return ledger.stock.get(sku) ?? 0;
}

export function record(ledger: Ledger, entry: string): void {
  ledger.journal.push(entry);
}

/** Sets the quantity of `sku`; at zero the SKU is removed and the depletion journaled. */
export function settle(ledger: Ledger, sku: string, onHand: number): void {
  if (onHand > 0) {
    ledger.stock.set(sku, onHand);
    return;
  }
  ledger.stock.delete(sku);
  record(ledger, `depleted ${sku}`);
}
