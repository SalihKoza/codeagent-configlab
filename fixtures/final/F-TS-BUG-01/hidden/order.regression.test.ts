// Regression: behavior that must stay unchanged (statement items 2, 3, 5-9).
import { test } from "node:test";
import assert from "node:assert/strict";
import * as api from "../src/index";
import {
  CycleError,
  DependencyEdge,
  DuplicateTargetError,
  resolveBuildOrder,
  UnknownTargetError,
} from "../src/index";

type Pair = [string, string];

const toEdges = (pairs: Pair[]): DependencyEdge[] =>
  pairs.map(([dependency, dependent]) => ({ dependency, dependent }));

const run = (targets: string[], pairs: Pair[]): string[] => resolveBuildOrder(targets, toEdges(pairs));

function thrown(fn: () => unknown): unknown {
  try {
    fn();
  } catch (err) {
    return err;
  }
  assert.ok(false, "expected an error to be thrown");
  return undefined;
}

test("longer chain declared in reverse", () => {
  const order = run(["w3", "w2", "w1", "w0"], [["w0", "w1"], ["w1", "w2"], ["w2", "w3"]]);
  assert.deepStrictEqual(order, ["w0", "w1", "w2", "w3"]);
});

test("diamond declared bottom-up", () => {
  const order = run(["d", "b", "c", "a"], [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]]);
  assert.deepStrictEqual(order, ["a", "b", "c", "d"]);
});

test("a newly ready target declared earlier goes before an older ready one", () => {
  const order = run(["e", "f", "g", "h", "i"], [["h", "e"], ["i", "f"], ["i", "g"]]);
  assert.deepStrictEqual(order, ["h", "e", "i", "f", "g"]);
});

test("several sources feeding one target", () => {
  const order = run(["out", "s1", "s2", "s3"], [["s3", "out"], ["s1", "out"], ["s2", "out"]]);
  assert.deepStrictEqual(order, ["s1", "s2", "s3", "out"]);
});

test("edge order does not affect the result", () => {
  const targets = ["r4", "r1", "r3", "r2"];
  const a = run(targets, [["r1", "r2"], ["r2", "r3"], ["r1", "r4"]]);
  const b = run(targets, [["r1", "r4"], ["r2", "r3"], ["r1", "r2"]]);
  assert.deepStrictEqual(a, ["r1", "r4", "r2", "r3"]);
  assert.deepStrictEqual(b, a);
});

test("repeated edges in a connected graph", () => {
  const order = run(["y", "x", "z"], [["x", "y"], ["x", "y"], ["y", "z"], ["x", "y"]]);
  assert.deepStrictEqual(order, ["x", "y", "z"]);
});

test("cycle error type, name, message and blocked targets", () => {
  const err = thrown(() =>
    run(["k", "l", "m", "n", "o"], [["k", "l"], ["l", "m"], ["m", "n"], ["n", "l"], ["n", "o"]]),
  );
  assert.ok(err instanceof CycleError);
  assert.ok(err instanceof Error);
  const e = err as CycleError;
  assert.strictEqual(e.name, "CycleError");
  assert.deepStrictEqual(e.targets, ["l", "m", "n", "o"]);
  assert.strictEqual(e.message, "Dependency cycle detected among targets: l, m, n, o");
});

test("a self-dependency is a cycle", () => {
  const err = thrown(() => run(["a", "b"], [["a", "b"], ["b", "b"]]));
  assert.ok(err instanceof CycleError);
  assert.deepStrictEqual((err as CycleError).targets, ["b"]);
});

test("cycle targets are listed in declaration order", () => {
  const err = thrown(() => run(["c3", "c1", "c2"], [["c1", "c2"], ["c2", "c3"], ["c3", "c1"]]));
  assert.ok(err instanceof CycleError);
  assert.deepStrictEqual((err as CycleError).targets, ["c3", "c1", "c2"]);
});

test("unknown target error details", () => {
  const err = thrown(() => run(["a", "b"], [["a", "b"], ["ghost", "a"]]));
  assert.ok(err instanceof UnknownTargetError);
  assert.ok(err instanceof Error);
  const e = err as UnknownTargetError;
  assert.strictEqual(e.name, "UnknownTargetError");
  assert.strictEqual(e.target, "ghost");
  assert.strictEqual(e.message, "Unknown target in dependency edge: ghost");
});

test("unknown dependency is reported before unknown dependent", () => {
  const err = thrown(() => run(["a"], [["first", "second"]]));
  assert.ok(err instanceof UnknownTargetError);
  assert.strictEqual((err as UnknownTargetError).target, "first");
});

test("unknown target is reported before a cycle", () => {
  const err = thrown(() => run(["a", "b"], [["a", "b"], ["b", "a"], ["a", "zz"]]));
  assert.ok(err instanceof UnknownTargetError);
  assert.strictEqual((err as UnknownTargetError).target, "zz");
});

test("duplicate target error details and precedence", () => {
  const err = thrown(() => run(["a", "b", "b", "a"], [["a", "nope"]]));
  assert.ok(err instanceof DuplicateTargetError);
  assert.ok(err instanceof Error);
  const e = err as DuplicateTargetError;
  assert.strictEqual(e.name, "DuplicateTargetError");
  assert.strictEqual(e.target, "b");
  assert.strictEqual(e.message, "Duplicate target: b");
});

test("empty input gives an empty array", () => {
  const order: string[] = resolveBuildOrder([], []);
  assert.ok(Array.isArray(order));
  assert.strictEqual(order.length, 0);
});

test("public exports and signature", () => {
  assert.strictEqual(typeof api.resolveBuildOrder, "function");
  assert.strictEqual(api.resolveBuildOrder.length, 2);
  for (const cls of [api.CycleError, api.UnknownTargetError, api.DuplicateTargetError]) {
    assert.strictEqual(typeof cls, "function");
    assert.ok(cls.prototype instanceof Error);
  }
});

test("inputs are not modified and a new array is returned", () => {
  const targets = Object.freeze(["b", "a", "c"]);
  const edges: readonly DependencyEdge[] = Object.freeze([
    Object.freeze({ dependency: "a", dependent: "b" }),
    Object.freeze({ dependency: "b", dependent: "c" }),
  ]);
  const first = resolveBuildOrder(targets, edges);
  assert.deepStrictEqual(first, ["a", "b", "c"]);
  assert.notStrictEqual(first, targets);
  first.reverse();
  assert.deepStrictEqual(resolveBuildOrder(targets, edges), ["a", "b", "c"]);
  assert.deepStrictEqual([...targets], ["b", "a", "c"]);
});
