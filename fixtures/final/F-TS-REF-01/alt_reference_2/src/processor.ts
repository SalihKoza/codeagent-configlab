import { UnsupportedOpError } from "./errors";
import { opHandlers } from "./handlers";
import type { Ledger, Outcome, Request } from "./types";

/**
 * Applies one request to `ledger` and returns its outcome; dispatch goes through `opHandlers`.
 * Any other `op` throws UnsupportedOpError before parameters are read.
 */
export function processRequest(request: Request, ledger: Ledger): Outcome {
  const op = request.op;
  if (!Object.hasOwn(opHandlers, op)) {
    throw new UnsupportedOpError(op);
  }
  const operation = opHandlers[op];
  return operation.handle(request.params ?? {}, ledger);
}
