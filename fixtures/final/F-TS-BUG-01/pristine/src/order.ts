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
  const position = new Map<string, number>();
  targets.forEach((target, index) => {
    if (position.has(target)) {
      throw new DuplicateTargetError(target);
    }
    position.set(target, index);
  });
  for (const edge of edges) {
    for (const name of [edge.dependency, edge.dependent]) {
      if (!position.has(name)) {
        throw new UnknownTargetError(name);
      }
    }
  }

  const pending = new Map<string, number>();
  const dependents = new Map<string, string[]>();
  for (const { dependency, dependent } of edges) {
    if (!pending.has(dependency)) {
      pending.set(dependency, 0);
      dependents.set(dependency, []);
    }
    if (!pending.has(dependent)) {
      pending.set(dependent, 0);
      dependents.set(dependent, []);
    }
    pending.set(dependent, pending.get(dependent)! + 1);
    dependents.get(dependency)!.push(dependent);
  }

  const byDeclaration = (a: string, b: string) => position.get(a)! - position.get(b)!;
  const ready = [...pending.keys()].filter((name) => pending.get(name) === 0);
  const order: string[] = [];
  while (ready.length > 0) {
    ready.sort(byDeclaration);
    const next = ready.shift()!;
    order.push(next);
    for (const dependent of dependents.get(next)!) {
      const remaining = pending.get(dependent)! - 1;
      pending.set(dependent, remaining);
      if (remaining === 0) {
        ready.push(dependent);
      }
    }
  }

  if (order.length < pending.size) {
    const placed = new Set(order);
    const blocked = [...pending.keys()].filter((name) => !placed.has(name)).sort(byDeclaration);
    throw new CycleError(blocked);
  }
  return order;
}
