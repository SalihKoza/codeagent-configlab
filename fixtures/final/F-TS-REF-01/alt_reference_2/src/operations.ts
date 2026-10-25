import { ShortageError } from "./errors";
import { readDelta, readQty, readReason, readSku } from "./params";
import type { Ledger, Outcome } from "./types";

export type Params = Readonly<Record<string, unknown>>;

export interface Operation {
  handle(params: Params, ledger: Ledger): Outcome;
}

abstract class StockChange implements Operation {
  abstract handle(params: Params, ledger: Ledger): Outcome;

  protected apply(ledger: Ledger, sku: string, onHand: number): void {
    if (onHand === 0) {
      ledger.stock.delete(sku);
      ledger.journal.push(`depleted ${sku}`);
    } else {
      ledger.stock.set(sku, onHand);
    }
  }
}

export class Receive implements Operation {
  handle(params: Params, ledger: Ledger): Outcome {
    const sku = readSku("receive", params);
    const qty = readQty("receive", params);
    const current = ledger.stock.get(sku);
    if (current === undefined) {
      ledger.journal.push(`new ${sku}`);
    }
    ledger.stock.set(sku, (current ?? 0) + qty);
    ledger.journal.push(`receive ${sku} +${qty}`);
    return { op: "receive", onHand: (current ?? 0) + qty };
  }
}

export class Ship extends StockChange {
  handle(params: Params, ledger: Ledger): Outcome {
    const sku = readSku("ship", params);
    const qty = readQty("ship", params);
    const available = ledger.stock.get(sku) ?? 0;
    if (qty > available) {
      throw new ShortageError(sku, qty, available);
    }
    ledger.journal.push(`ship ${sku} -${qty}`);
    this.apply(ledger, sku, available - qty);
    return { op: "ship", onHand: available - qty };
  }
}

export class Adjust extends StockChange {
  handle(params: Params, ledger: Ledger): Outcome {
    const sku = readSku("adjust", params);
    const delta = readDelta("adjust", params);
    const reason = readReason("adjust", params);
    const available = ledger.stock.get(sku) ?? 0;
    const onHand = available + delta;
    if (onHand < 0) {
      throw new ShortageError(sku, -delta, available);
    }
    ledger.journal.push(`adjust ${sku} ${delta < 0 ? "-" : "+"}${Math.abs(delta)} ${reason}`);
    this.apply(ledger, sku, onHand);
    return { op: "adjust", onHand };
  }
}

export class Count implements Operation {
  handle(params: Params, ledger: Ledger): Outcome {
    const sku = readSku("count", params);
    return { op: "count", onHand: ledger.stock.get(sku) ?? 0 };
  }
}

export class Report implements Operation {
  handle(_params: Params, ledger: Ledger): Outcome {
    const skus = Array.from(ledger.stock.keys()).sort();
    ledger.journal.push(`report ${skus.length}`);
    return { op: "report", lines: skus.map((sku) => `${sku}=${ledger.stock.get(sku)}`) };
  }
}
