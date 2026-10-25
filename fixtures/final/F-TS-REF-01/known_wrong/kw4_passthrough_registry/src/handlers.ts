import { dispatchLegacy } from "./legacy";
import type { Ledger, Outcome } from "./types";

export type Params = Readonly<Record<string, unknown>>;
export type OpHandler = (params: Params, ledger: Ledger) => Outcome;

/** Operation identifier -> handler. */
export const opHandlers: ReadonlyMap<string, OpHandler> = new Map<string, OpHandler>([
  ["receive", (params, ledger) => dispatchLegacy({ op: "receive", params }, ledger)],
  ["ship", (params, ledger) => dispatchLegacy({ op: "ship", params }, ledger)],
  ["adjust", (params, ledger) => dispatchLegacy({ op: "adjust", params }, ledger)],
  ["count", (params, ledger) => dispatchLegacy({ op: "count", params }, ledger)],
  ["report", (params, ledger) => dispatchLegacy({ op: "report", params }, ledger)],
]);
