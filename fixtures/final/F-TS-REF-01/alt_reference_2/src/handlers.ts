import { Adjust, Count, Operation, Receive, Report, Ship } from "./operations";

function buildHandlers() {
  return {
    receive: new Receive(),
    ship: new Ship(),
    adjust: new Adjust(),
    count: new Count(),
    report: new Report(),
  };
}

/** Operation identifier -> handler object. */
export const opHandlers: Readonly<Record<string, Operation>> = Object.freeze(buildHandlers());
