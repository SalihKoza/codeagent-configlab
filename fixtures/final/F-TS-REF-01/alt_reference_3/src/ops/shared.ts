import type { Ledger } from "../types";

export type Params = Readonly<Record<string, unknown>>;

export function finish(ledger: Ledger, sku: string, onHand: number): void {
  if (onHand === 0) {
    ledger.stock.delete(sku);
    ledger.journal.push(`depleted ${sku}`);
  } else {
    ledger.stock.set(sku, onHand);
  }
}
