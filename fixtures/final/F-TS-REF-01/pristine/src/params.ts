import { ParamError } from "./errors";

type Params = Readonly<Record<string, unknown>>;

const SKU_PATTERN = /^[A-Z][A-Z0-9-]{0,15}$/;
const MAX_QUANTITY = 10000;
const MAX_REASON_LENGTH = 40;

/** `params.sku`: an uppercase letter followed by up to 15 of A-Z, 0-9 or "-". */
export function readSku(op: string, params: Params): string {
  const sku = params.sku;
  if (typeof sku !== "string" || !SKU_PATTERN.test(sku)) {
    throw new ParamError(op, "sku");
  }
  return sku;
}

/** `params.qty`: an integer from 1 to 10000. */
export function readQty(op: string, params: Params): number {
  const qty = params.qty;
  if (typeof qty !== "number" || !Number.isInteger(qty) || qty < 1 || qty > MAX_QUANTITY) {
    throw new ParamError(op, "qty");
  }
  return qty;
}

/** `params.delta`: a non-zero integer from -10000 to 10000. */
export function readDelta(op: string, params: Params): number {
  const delta = params.delta;
  if (typeof delta !== "number" || !Number.isInteger(delta) || delta === 0
      || Math.abs(delta) > MAX_QUANTITY) {
    throw new ParamError(op, "delta");
  }
  return delta;
}

/** `params.reason`: a string that is 1 to 40 characters long after trimming; returned trimmed. */
export function readReason(op: string, params: Params): string {
  const reason = params.reason;
  if (typeof reason !== "string") {
    throw new ParamError(op, "reason");
  }
  const trimmed = reason.trim();
  if (trimmed.length === 0 || trimmed.length > MAX_REASON_LENGTH) {
    throw new ParamError(op, "reason");
  }
  return trimmed;
}
