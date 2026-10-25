import { UnsupportedOpError } from "./errors";
import { opHandlers } from "./handlers";
import type { Ledger, Outcome, Request } from "./types";

type OpName = keyof typeof opHandlers;

function isOpName(op: string): op is OpName {
  return Object.keys(opHandlers).includes(op);
}

/**
 * Applies one request to `ledger` and returns its outcome; dispatch goes through `opHandlers`.
 * Any other `op` throws UnsupportedOpError before parameters are read.
 */
export function processRequest({ op, params = {} }: Request, ledger: Ledger): Outcome {
  if (!isOpName(op)) {
    throw new UnsupportedOpError(op);
  }
  const run = opHandlers[op];
  return run(params, ledger);
}
