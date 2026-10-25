/** Thrown when `request.op` is not one of the supported operation identifiers. */
export class UnsupportedOpError extends Error {
  readonly op: string;

  constructor(op: string) {
    super(`Unsupported operation: ${op}`);
    this.name = "UnsupportedOpError";
    this.op = op;
  }
}

/** Thrown when a parameter of a supported operation is missing or invalid. */
export class ParamError extends Error {
  readonly op: string;
  readonly param: string;

  constructor(op: string, param: string) {
    super(`${op}: invalid ${param}`);
    this.name = "ParamError";
    this.op = op;
    this.param = param;
  }
}

/** Thrown when a request would make the on-hand quantity of `sku` negative. */
export class ShortageError extends Error {
  readonly sku: string;
  readonly requested: number;
  readonly available: number;

  constructor(sku: string, requested: number, available: number) {
    super(`Insufficient stock for ${sku}: requested ${requested}, available ${available}`);
    this.name = "ShortageError";
    this.sku = sku;
    this.requested = requested;
    this.available = available;
  }
}
