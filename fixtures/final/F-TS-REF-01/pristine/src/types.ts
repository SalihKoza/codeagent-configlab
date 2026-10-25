/** A request: the operation identifier and its parameters (missing `params` means `{}`). */
export interface Request {
  readonly op: string;
  readonly params?: Readonly<Record<string, unknown>>;
}

/** In-memory stock ledger: on-hand quantity per SKU (always > 0) and an append-only journal. */
export interface Ledger {
  readonly stock: Map<string, number>;
  readonly journal: string[];
}

/** Result of a successful request. `onHand` for receive/ship/adjust/count, `lines` for report. */
export interface Outcome {
  readonly op: string;
  readonly onHand?: number;
  readonly lines?: readonly string[];
}

/** A new, empty ledger. */
export function createLedger(): Ledger {
  return { stock: new Map<string, number>(), journal: [] };
}
