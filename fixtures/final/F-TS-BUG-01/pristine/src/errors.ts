/** Thrown when the same target name is declared more than once. */
export class DuplicateTargetError extends Error {
  readonly target: string;

  constructor(target: string) {
    super(`Duplicate target: ${target}`);
    this.name = "DuplicateTargetError";
    this.target = target;
  }
}

/** Thrown when a dependency edge names a target that was not declared. */
export class UnknownTargetError extends Error {
  readonly target: string;

  constructor(target: string) {
    super(`Unknown target in dependency edge: ${target}`);
    this.name = "UnknownTargetError";
    this.target = target;
  }
}

/**
 * Thrown when the dependency edges contain a cycle.
 *
 * `targets` lists every declared target that cannot be placed in a build order (the targets on a
 * cycle and everything that depends on them), in declaration order.
 */
export class CycleError extends Error {
  readonly targets: string[];

  constructor(targets: string[]) {
    super(`Dependency cycle detected among targets: ${targets.join(", ")}`);
    this.name = "CycleError";
    this.targets = targets;
  }
}
