import { adjust } from "./ops/adjust";
import { count, report } from "./ops/query";
import { receive } from "./ops/receive";
import { ship } from "./ops/ship";

/** Operation identifier -> handler. */
export const opHandlers = { receive, ship, adjust, count, report } as const;
