import { CycleError, DuplicateTargetError, UnknownTargetError } from "./errors";

/** `dependency` must be built before `dependent`. */
export interface DependencyEdge {
  readonly dependency: string;
  readonly dependent: string;
}

/**
 * Returns an order in which the declared `targets` can be built.
 *
 * - Every declared target appears exactly once; no other name appears.
 * - For every edge, `dependency` comes before `dependent`. Repeating an edge has the same effect
 *   as listing it once.
 * - Ties are broken by declaration order: a target is ready once all of its dependencies have been
 *   placed, and each next position is given to the earliest-declared ready target that has not
 *   been placed yet.
 *
 * Errors, checked in this order:
 * - `DuplicateTargetError` for the first target name that is declared a second time;
 * - `UnknownTargetError` for the first edge (in `edges` order) that names an undeclared target,
 *   checking its `dependency` before its `dependent`;
 * - `CycleError` if the edges contain a cycle (see `CycleError.targets`).
 *
 * The inputs are not modified; a new array is returned. No targets give an empty array.
 */
export function resolveBuildOrder(
  targets: readonly string[],
  edges: readonly DependencyEdge[],
): string[] {
  const requires = new Map<string, Set<string>>();
  for (const target of targets) {
    if (requires.has(target)) {
      throw new DuplicateTargetError(target);
    }
    requires.set(target, new Set());
  }
  for (const { dependency, dependent } of edges) {
    if (!requires.has(dependency)) {
      throw new UnknownTargetError(dependency);
    }
    if (!requires.has(dependent)) {
      throw new UnknownTargetError(dependent);
    }
    requires.get(dependent)!.add(dependency);
  }

  // Repeatedly take the first declared target whose dependencies are all placed.
  const placed = new Set<string>();
  const order: string[] = [];
  while (order.length < targets.length) {
    const next = targets.find(
      (name) => !placed.has(name) && [...requires.get(name)!].every((dep) => placed.has(dep)),
    );
    if (next === undefined) {
      throw new CycleError(targets.filter((name) => !placed.has(name)));
    }
    placed.add(next);
    order.push(next);
  }
  return order;
}
