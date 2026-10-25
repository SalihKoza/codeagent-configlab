# build-order — `resolveBuildOrder` drops targets that have no dependency edges

`src/order.ts` provides `resolveBuildOrder(targets, edges)`, re-exported from `src/index.ts`. It
receives the declared build targets (`targets`, an array of unique names) and dependency edges
(`edges`, objects `{ dependency, dependent }` meaning that `dependency` must be built before
`dependent`), and returns an array of target names in an order in which they can be built.

## Bug report

A target that is declared but appears in no edge — neither as `dependency` nor as `dependent` — is
missing from the returned order:

```ts
resolveBuildOrder(
  ["docs", "compile", "test", "lint", "package"],
  [
    { dependency: "compile", dependent: "test" },
    { dependency: "test", dependent: "package" },
    { dependency: "compile", dependent: "package" },
  ],
);
// actual:   ["compile", "test", "package"]
// expected: ["docs", "compile", "test", "lint", "package"]
```

## Required behavior of `resolveBuildOrder(targets, edges)`

Fix `resolveBuildOrder` so that, for every input, it follows this contract:

1. Every declared target appears in the returned order **exactly once**, whether or not it appears
   in any edge.
2. No name other than the declared targets appears in the result. An edge that names an undeclared
   target still raises `UnknownTargetError` (see item 7); it never adds that name to the order.
3. For every edge, `dependency` comes before `dependent` in the result.
4. A declared target with no incoming and no outgoing edge is a normal target without
   dependencies; it is included like any other target.
5. Tie-break (declaration order). A target is *ready* when all of its dependencies have already
   been placed in the result. The result is built one position at a time, and each position is
   given to the **earliest-declared ready target** that has not been placed yet. Equivalently: the
   result is what you get by repeatedly taking the first target, in declaration order, that has
   not been placed yet and whose dependencies have all been placed. A target with no dependencies
   is ready from the start, so a target without edges is placed as soon as no earlier-declared
   ready target is still waiting; it is not simply moved to the end. In the example above, `docs`
   is placed first because it is declared first and is ready; `lint` is placed after `test`
   because `test` is declared before `lint` and is ready at that point.
6. Cycle behavior is unchanged: if the edges contain a cycle (including an edge from a target to
   itself), `resolveBuildOrder` raises `CycleError`. Its `targets` property lists every target
   that cannot be placed (the targets on a cycle and everything that depends on them, directly or
   indirectly), in declaration order, and its message is
   `Dependency cycle detected among targets: ` followed by those names joined with `", "`. A target
   without edges can always be placed, so it never appears in `CycleError.targets`, and it never
   suppresses the error.
7. Input validation is unchanged and happens before ordering: the first target name that is
   declared a second time raises `DuplicateTargetError`; otherwise the first edge (in `edges`
   order) that names an undeclared target raises `UnknownTargetError`, checking its `dependency`
   before its `dependent`. Error classes, `name`, `target` properties and messages stay as they are.
   Listing the same edge more than once has the same effect as listing it once.
8. `resolveBuildOrder([], [])` returns an empty array.
9. The exported names (`resolveBuildOrder`, `DependencyEdge`, `CycleError`, `UnknownTargetError`,
   `DuplicateTargetError`), the function signature and the return type (`string[]`) stay
   unchanged. The function returns a new array and does not modify `targets` or `edges`.

The existing behavior for inputs in which every declared target appears in at least one edge
already follows items 1-9 and must not change.

## Constraints

- Do not add dependencies.
- Do not change the public API or the behavior described above beyond what the contract requires.

## Running the public tests

    npm run build
    npm test
