import { opHandlers } from "./handlers";
import { dispatchLegacy } from "./legacy";
import type { Ledger, Outcome, Request } from "./types";

/** Applies one request to `ledger`; shipping still goes through the former dispatcher. */
export function processRequest(request: Request, ledger: Ledger): Outcome {
  const handler = request.op === "ship" ? undefined : opHandlers.get(request.op);
  if (handler === undefined) {
    return dispatchLegacy(request, ledger);
  }
  return handler(request.params ?? {}, ledger);
}
