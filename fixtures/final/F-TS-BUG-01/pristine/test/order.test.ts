import { test } from "node:test";
import assert from "node:assert/strict";
import {
  CycleError,
  DependencyEdge,
  DuplicateTargetError,
  resolveBuildOrder,
  UnknownTargetError,
} from "../src/index";

const edge = (dependency: string, dependent: string): DependencyEdge => ({ dependency, dependent });

function thrown(fn: () => unknown): unknown {
  try {
    fn();
  } catch (err) {
    return err;
  }
  assert.ok(false, "expected an error to be thrown");
  return undefined;
}

test("a chain is ordered from its first dependency to its last dependent", () => {
  const order = resolveBuildOrder(["c", "b", "a"], [edge("a", "b"), edge("b", "c")]);
  assert.deepStrictEqual(order, ["a", "b", "c"]);
});

test("a diamond places both middle targets in declaration order", () => {
  const order = resolveBuildOrder(
    ["top", "left", "right", "base"],
    [edge("base", "left"), edge("base", "right"), edge("left", "top"), edge("right", "top")],
  );
  assert.deepStrictEqual(order, ["base", "left", "right", "top"]);
});

test("each position goes to the earliest-declared ready target", () => {
  const order = resolveBuildOrder(["p", "q", "r", "s"], [edge("r", "p"), edge("s", "q")]);
  assert.deepStrictEqual(order, ["r", "p", "s", "q"]);
});

test("a repeated edge counts once", () => {
  const order = resolveBuildOrder(["b", "a"], [edge("a", "b"), edge("a", "b")]);
  assert.deepStrictEqual(order, ["a", "b"]);
});

test("a cycle raises CycleError listing the targets that cannot be placed", () => {
  const err = thrown(() =>
    resolveBuildOrder(
      ["a", "b", "c", "d"],
      [edge("a", "b"), edge("b", "c"), edge("c", "b"), edge("c", "d")],
    ),
  );
  assert.ok(err instanceof CycleError);
  assert.deepStrictEqual((err as CycleError).targets, ["b", "c", "d"]);
  assert.strictEqual((err as CycleError).message, "Dependency cycle detected among targets: b, c, d");
});

test("an edge naming an undeclared target raises UnknownTargetError", () => {
  const err = thrown(() => resolveBuildOrder(["a"], [edge("a", "missing")]));
  assert.ok(err instanceof UnknownTargetError);
  assert.strictEqual((err as UnknownTargetError).target, "missing");
});

test("declaring a target twice raises DuplicateTargetError", () => {
  const err = thrown(() => resolveBuildOrder(["a", "b", "a"], [edge("a", "b")]));
  assert.ok(err instanceof DuplicateTargetError);
  assert.strictEqual((err as DuplicateTargetError).target, "a");
});

test("no targets give an empty order", () => {
  assert.deepStrictEqual(resolveBuildOrder([], []), []);
});
