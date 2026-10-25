// Acceptance: declared targets without dependency edges (statement items 1-6, 8).
import { test } from "node:test";
import assert from "node:assert/strict";
import { CycleError, DependencyEdge, resolveBuildOrder } from "../src/index";

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

// Items 1-3: a permutation of the declared targets in which every dependency precedes its dependent.
function assertValidOrder(order: string[], targets: string[], pairs: Pair[]): void {
  assert.deepStrictEqual([...order].sort(), [...targets].sort(), "each declared target exactly once");
  for (const [dependency, dependent] of pairs) {
    assert.ok(
      order.indexOf(dependency) < order.indexOf(dependent),
      `${dependency} must come before ${dependent} in ${JSON.stringify(order)}`,
    );
  }
}

// Item 5, second sentence, verbatim: repeatedly take the first target in declaration order that
// is not yet placed and whose dependencies have all been placed.
function ruleOrder(targets: string[], pairs: Pair[]): string[] {
  const placed: string[] = [];
  while (placed.length < targets.length) {
    const next = targets.find(
      (t) => !placed.includes(t) && pairs.every(([dep, dt]) => dt !== t || placed.includes(dep)),
    );
    if (next === undefined) {
      throw new Error("generator produced a cycle");
    }
    placed.push(next);
  }
  return placed;
}

interface Case {
  targets: string[];
  pairs: Pair[];
  expected: string[];
}

// Every expected order below follows from the tie-break rule (item 5) applied step by step.
const CASES: Record<string, Case> = {
  isolatedFirst: {
    targets: ["iso", "a", "b", "c"],
    pairs: [["a", "b"], ["b", "c"]],
    expected: ["iso", "a", "b", "c"],
  },
  isolatedBetween: {
    targets: ["a", "iso", "b", "c"],
    pairs: [["a", "b"], ["b", "c"]],
    expected: ["a", "iso", "b", "c"],
  },
  isolatedLast: {
    targets: ["a", "b", "c", "iso"],
    pairs: [["a", "b"], ["b", "c"]],
    expected: ["a", "b", "c", "iso"],
  },
  severalIsolated: {
    targets: ["m", "c", "n", "b", "o", "a"],
    pairs: [["a", "b"], ["b", "c"]],
    expected: ["m", "n", "o", "a", "b", "c"],
  },
  components: {
    targets: ["k1", "j2", "i3", "h4", "g5", "f6", "e7"],
    pairs: [["i3", "k1"], ["f6", "h4"], ["h4", "j2"]],
    expected: ["i3", "k1", "g5", "f6", "h4", "j2", "e7"],
  },
  readyBeforeIsolated: {
    targets: ["b2", "z", "a1", "y"],
    pairs: [["a1", "b2"]],
    expected: ["z", "a1", "b2", "y"],
  },
  sourceAndIsolated: {
    targets: ["s", "t", "lone"],
    pairs: [["s", "t"]],
    expected: ["s", "t", "lone"],
  },
  repeatedEdgeWithIsolated: {
    targets: ["d1", "lone", "d2"],
    pairs: [["d1", "d2"], ["d1", "d2"]],
    expected: ["d1", "lone", "d2"],
  },
  unrelatedNames: {
    targets: ["zeta-9", "alpha.core", "m_3", "Q"],
    pairs: [["m_3", "zeta-9"]],
    expected: ["alpha.core", "m_3", "zeta-9", "Q"],
  },
};

test("statement example: unconnected targets are kept", () => {
  const order = run(
    ["docs", "compile", "test", "lint", "package"],
    [["compile", "test"], ["test", "package"], ["compile", "package"]],
  );
  assert.deepStrictEqual(order, ["docs", "compile", "test", "lint", "package"]);
});

test("isolated target declared before a chain", () => {
  const c = CASES.isolatedFirst;
  assert.deepStrictEqual(run(c.targets, c.pairs), c.expected);
});

test("isolated target declared between chain targets", () => {
  const c = CASES.isolatedBetween;
  assert.deepStrictEqual(run(c.targets, c.pairs), c.expected);
});

test("isolated target declared after a chain", () => {
  const c = CASES.isolatedLast;
  assert.deepStrictEqual(run(c.targets, c.pairs), c.expected);
});

test("several isolated targets mixed with a chain", () => {
  const c = CASES.severalIsolated;
  assert.deepStrictEqual(run(c.targets, c.pairs), c.expected);
});

test("only isolated targets keep declaration order", () => {
  assert.deepStrictEqual(run(["q", "e", "d"], []), ["q", "e", "d"]);
});

test("a single isolated target", () => {
  assert.deepStrictEqual(run(["solo"], []), ["solo"]);
});

test("disconnected components plus isolated targets", () => {
  const c = CASES.components;
  assert.deepStrictEqual(run(c.targets, c.pairs), c.expected);
});

test("a ready target declared earlier is placed before a later isolated one", () => {
  const c = CASES.readyBeforeIsolated;
  assert.deepStrictEqual(run(c.targets, c.pairs), c.expected);
});

test("targets that appear in edges are not repeated", () => {
  const c = CASES.sourceAndIsolated;
  const order = run(c.targets, c.pairs);
  for (const t of c.targets) {
    assert.strictEqual(order.filter((x) => x === t).length, 1, `${t} appears once`);
  }
  assert.deepStrictEqual(order, c.expected);
});

test("repeated edges together with an isolated target", () => {
  const c = CASES.repeatedEdgeWithIsolated;
  assert.deepStrictEqual(run(c.targets, c.pairs), c.expected);
});

test("target names unrelated to any example", () => {
  const c = CASES.unrelatedNames;
  assert.deepStrictEqual(run(c.targets, c.pairs), c.expected);
});

test("every declared target appears exactly once", () => {
  for (const [label, c] of Object.entries(CASES)) {
    const order = run(c.targets, c.pairs);
    assert.strictEqual(order.length, c.targets.length, `${label}: length`);
    assert.deepStrictEqual([...order].sort(), [...c.targets].sort(), `${label}: same targets`);
  }
});

test("every dependency precedes its dependent", () => {
  for (const c of Object.values(CASES)) {
    assertValidOrder(run(c.targets, c.pairs), c.targets, c.pairs);
  }
});

test("generated acyclic graphs follow the declaration-order rule", () => {
  let seed = 0x5eed1234;
  const rand = (n: number): number => {
    seed = (Math.imul(seed, 1103515245) + 12345) >>> 0;
    return (seed >>> 8) % n;
  };
  const shuffle = <T>(xs: T[]): T[] => {
    const out = [...xs];
    for (let i = out.length - 1; i > 0; i--) {
      const j = rand(i + 1);
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  };
  for (let g = 0; g < 60; g++) {
    const size = 1 + rand(8);
    const targets = shuffle(Array.from({ length: size }, (_, k) => `v${g}x${k}`));
    const topo = shuffle(targets);
    const pairs: Pair[] = [];
    for (let i = 0; i < topo.length; i++) {
      for (let j = i + 1; j < topo.length; j++) {
        if (rand(10) < 3) {
          pairs.push([topo[i], topo[j]]);
          if (rand(10) === 0) {
            pairs.push([topo[i], topo[j]]);
          }
        }
      }
    }
    if (g % 2 === 0) {
      targets.splice(rand(targets.length + 1), 0, `w${g}`);
    }
    const order = run(targets, pairs);
    assertValidOrder(order, targets, pairs);
    assert.deepStrictEqual(order, ruleOrder(targets, pairs), `graph ${g}`);
  }
});

test("a cycle is still reported when isolated targets are declared", () => {
  const err = thrown(() => run(["u", "a", "v", "b"], [["a", "b"], ["b", "a"]]));
  assert.ok(err instanceof CycleError);
  assert.deepStrictEqual((err as CycleError).targets, ["a", "b"]);
  assert.strictEqual((err as CycleError).message, "Dependency cycle detected among targets: a, b");
});

test("a self-dependency is still a cycle when isolated targets are declared", () => {
  const err = thrown(() => run(["p", "self", "q"], [["self", "self"]]));
  assert.ok(err instanceof CycleError);
  assert.deepStrictEqual((err as CycleError).targets, ["self"]);
});

test("a cycle in one component with an acyclic component and isolated targets", () => {
  const err = thrown(() =>
    run(["g", "h", "i", "j", "k"], [["g", "h"], ["i", "j"], ["j", "i"]]),
  );
  assert.ok(err instanceof CycleError);
  assert.deepStrictEqual((err as CycleError).targets, ["i", "j"]);
});

test("no declared targets give an empty order", () => {
  assert.deepStrictEqual(resolveBuildOrder([], []), []);
});
