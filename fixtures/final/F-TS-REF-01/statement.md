# stock-ledger — move operation dispatch into a handler registry

`processRequest(request, ledger)` (`src/processor.ts`, exported from `src/index.ts`) applies one
inventory request to an in-memory ledger. Today it is one function with a `switch (request.op)` in
which every operation is implemented inline. Adding or changing an operation means editing that
function. Restructure the dispatch so that every operation has its own handler, registered in a
named registry, **without changing any observable behavior**.

## Required structure

Create `src/handlers.ts` exporting a registry variable named **`opHandlers`** that maps each of the
five operation identifiers `receive`, `ship`, `adjust`, `count`, `report` to its handler, and make
`processRequest` dispatch through it. `processRequest` stays exported from `src/index.ts`.

A *handler* is a function `(params, ledger) => Outcome`, or an object (for example a class instance)
with a `handle(params, ledger)` method. How you build the registry is up to you — a `Map`, a plain
or prototype-less object, an object literal (also shorthand), a factory function, or registration
calls — as long as the rules below hold. Handlers may live in any files under `src/` and may share
helpers.

The structure is checked statically on `src/**/*.ts` with the TypeScript compiler API (symbols are
resolved through imports, exports and aliases; nothing is executed and no text matching is used).
Terms:

- **Registry entry**: an operation identifier written literally — an identifier or string key of an
  object-literal property or method, a string-literal call argument, or the first element of a
  two-element array literal — together with its handler (the property value, the next argument,
  or the second element). It counts when it appears (a) inside the initializer of `opHandlers` or
  inside a `src` function called from it (directly or transitively), (b) in `opHandlers.set(k, h)`,
  `opHandlers[k] = h` or `opHandlers.k = h`, or (c) in a call of a `src` function whose body does
  (b) with two of its own parameters. Entries computed at run time (for example in a loop over a
  list of names) are not recognized.
- **Reaches**: code reaches a function, method, class or variable when it mentions it (an
  identifier or property name resolved by the type checker), transitively. A class contributes all
  of its members and its base classes; a variable contributes its initializer.
- **Dispatch path**: `processRequest` and everything it reaches, not counting what is reached only
  through `opHandlers` itself.
- **Op-derived value**: `request.op` (or `request["op"]`, or a destructured `op`) of
  `processRequest`'s first parameter, any variable initialized from one, and any parameter of a
  `src` function called with one.
- **Dispatcher**: a `src` function containing a `switch` with two or more operation identifiers as
  case labels, or equality comparisons against two or more different operation identifiers.

Rules:

- **S1** `src/handlers.ts` exports a variable named `opHandlers`.
- **S2** Each of the five operation identifiers has a registry entry whose handler is a function, a
  class instance (`new C(...)`), or an object literal with a `handle` member.
- **S3** The dispatch path looks up `opHandlers` with an op-derived key (`opHandlers[key]` or
  `opHandlers.get(key)`, possibly inside helper functions) and invokes the result (calling it, or
  calling a method on it such as `.handle(...)`).
- **S4** On the dispatch path an op-derived value is never a `switch` discriminant, an operand of a
  comparison (`===`, `!==`, `==`, `!=`, `<`, `>`, `<=`, `>=`), a bare condition, a key into
  anything other than `opHandlers`, or the subject of a membership test on anything other than
  `opHandlers` (`in`, `.has`, `.get`, `.includes`, `Object.hasOwn` and similar on `opHandlers`,
  `opHandlers.keys()` or `Object.keys(opHandlers)` are allowed). Using it in an error, in a
  string, or passing it on is fine. The dispatch path reaches no dispatcher.
- **S5** No handler (with everything it reaches) reaches `processRequest` or a dispatcher: handlers
  must not route back into a central dispatch.
- **S6** The operation behavior lives in the handlers: every handler reaches ledger state
  (`.stock` or `.journal`), and the dispatch path neither accesses ledger state nor constructs
  `ParamError` or `ShortageError`.

## Behavior (must stay exactly as it is)

Types (`src/types.ts`): `Request = { op: string; params?: Record<string, unknown> }` (missing
`params` means `{}`), `Ledger = { stock: Map<string, number>; journal: string[] }` (stock holds
only quantities > 0), `Outcome = { op; onHand? ; lines? }`, `createLedger()` returns a new empty
ledger. Errors (`src/errors.ts`):

- `UnsupportedOpError` — `name` `"UnsupportedOpError"`, `op`, message `Unsupported operation: <op>`;
- `ParamError` — `name` `"ParamError"`, `op`, `param`, message `<op>: invalid <param>`;
- `ShortageError` — `name` `"ShortageError"`, `sku`, `requested`, `available`, message
  `Insufficient stock for <sku>: requested <requested>, available <available>`.

Rules:

1. `op` must be exactly one of `receive`, `ship`, `adjust`, `count`, `report`. Any other value —
   including different case or spacing and names such as `toString` or `__proto__` — throws
   `UnsupportedOpError` before any parameter is read.
2. Parameters are validated in the order `sku`, then `qty` or `delta`, then `reason`; the first
   invalid one throws `ParamError(op, param)`:
   - `sku`: a string matching `^[A-Z][A-Z0-9-]{0,15}$`;
   - `qty`: an integer from 1 to 10000;
   - `delta`: a non-zero integer from -10000 to 10000;
   - `reason`: a string that is 1 to 40 characters long after trimming (used trimmed).
3. `receive {sku, qty}`: if the SKU is not on hand, journal `new <sku>`; then add `qty` and journal
   `receive <sku> +<qty>`. Outcome `{ op: "receive", onHand }`.
4. `ship {sku, qty}`: if fewer than `qty` are on hand (0 if absent), throw
   `ShortageError(sku, qty, available)`. Otherwise journal `ship <sku> -<qty>`; if nothing is left,
   remove the SKU and then journal `depleted <sku>`. Outcome `{ op: "ship", onHand }`.
5. `adjust {sku, delta, reason}`: starting from the on-hand quantity (0 if absent; no `new` entry),
   if the result would be negative throw `ShortageError(sku, -delta, available)`. Otherwise journal
   `adjust <sku> <+delta or -n> <reason>`; if the result is 0, remove the SKU and then journal
   `depleted <sku>`. Outcome `{ op: "adjust", onHand }`.
6. `count {sku}`: no change and no journal entry. Outcome `{ op: "count", onHand }` (0 if absent).
7. `report` (parameters ignored): journal `report <number of SKUs>`. Outcome
   `{ op: "report", lines }` with one `<sku>=<qty>` line per SKU, sorted by SKU in code-unit order.
8. A request that throws changes nothing. Requests and their params are never modified. Every
   outcome (and `lines` array) is a new object; outcomes have exactly the keys shown.
9. Exports (`processRequest`, `createLedger`, the types and the three error classes), the
   signature of `processRequest` and all error classes, properties and messages stay unchanged.

The public tests and the TSDoc in `src/processor.ts` describe the same behavior.

## Constraints

- Do not add dependencies.
- Do not change behavior; this is a pure restructuring.

## Running the public tests

    npm run build
    npm test
