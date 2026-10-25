import { UnsupportedOpError } from "./errors";
import { OpHandler, opHandlers } from "./handlers";
import type { Ledger, Outcome, Request } from "./types";

function selectHandler(op: string): OpHandler {
  const handler = op in opHandlers ? opHandlers[op] : undefined;
  if (handler === undefined) {
    throw new UnsupportedOpError(op);
  }
  return handler;
}

/**
 * Applies one request to `ledger` and returns its outcome; dispatch goes through `opHandlers`.
 * Any other `op` throws UnsupportedOpError before parameters are read.
 */
export function processRequest(request: Request, ledger: Ledger): Outcome {
  const { op, params } = request;
  return selectHandler(op)(params ?? {}, ledger);
}
