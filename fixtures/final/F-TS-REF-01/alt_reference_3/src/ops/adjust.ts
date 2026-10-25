import { ShortageError } from "../errors";
import { readDelta, readReason, readSku } from "../params";
import type { Ledger, Outcome } from "../types";
import { finish, Params } from "./shared";

function signed(delta: number): string {
  switch (Math.sign(delta)) {
    case 1:
      return `+${delta}`;
    default:
      return String(delta);
  }
}

export function adjust(params: Params, ledger: Ledger): Outcome {
  const sku = readSku("adjust", params);
  const delta = readDelta("adjust", params);
  const reason = readReason("adjust", params);
  const available = ledger.stock.get(sku) ?? 0;
  if (available + delta < 0) {
    throw new ShortageError(sku, -delta, available);
  }
  ledger.journal.push(`adjust ${sku} ${signed(delta)} ${reason}`);
  finish(ledger, sku, available + delta);
  return { op: "adjust", onHand: available + delta };
}
