import { UnsupportedOpError } from "./errors";
import { count, opHandlers } from "./handlers";
import type { Ledger, Outcome, Request } from "./types";

/**
 * Applies one request to `ledger` and returns its outcome.
 *
 * The handler for `request.op` is taken from `opHandlers` (see `src/handlers.ts` for the behavior
 * of each operation). Any other `op` throws UnsupportedOpError before parameters are read. A
 * request that throws changes nothing. The request is never modified.
 */
export function processRequest(request: Request, ledger: Ledger): Outcome {
  const handler = opHandlers.get(request.op) ?? (request.op === "count" ? count : undefined);
  if (handler === undefined) {
    throw new UnsupportedOpError(request.op);
  }
  return handler(request.params ?? {}, ledger);
}
