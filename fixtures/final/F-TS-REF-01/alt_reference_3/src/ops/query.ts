import { readSku } from "../params";
import type { Ledger, Outcome } from "../types";
import type { Params } from "./shared";

export function count(params: Params, ledger: Ledger): Outcome {
  return { op: "count", onHand: ledger.stock.get(readSku("count", params)) ?? 0 };
}

export function report(_params: Params, ledger: Ledger): Outcome {
  const lines: string[] = [];
  for (const sku of [...ledger.stock.keys()].sort()) {
    lines.push(`${sku}=${ledger.stock.get(sku)}`);
  }
  ledger.journal.push(`report ${lines.length}`);
  return { op: "report", lines };
}
