// Regression: existing canonical behavior that must stay unchanged (statement "Unchanged behavior").
import { test } from "node:test";
import assert from "node:assert/strict";
import * as api from "../src/index";
import {
  Command,
  CommandHandler,
  CommandRegistry,
  DuplicateCommandError,
  UnknownCommandError,
} from "../src/index";

// Records hold functions, which do not survive the test runner's error serialization; compare them
// by identity with plain boolean assertions instead.
function same(actual: unknown, expected: unknown, what = "value"): void {
  assert.ok(actual === expected, `${what}: expected the identical object`);
}

function sameList(actual: readonly unknown[], expected: readonly unknown[], what = "list"): void {
  assert.strictEqual(actual.length, expected.length, `${what}: length`);
  expected.forEach((item, i) => same(actual[i], item, `${what}[${i}]`));
}

function thrown(fn: () => unknown): unknown {
  try {
    fn();
  } catch (err) {
    return err;
  }
  assert.ok(false, "expected an error to be thrown");
  return undefined;
}

const tag = (label: string): CommandHandler => (args) => `${label}[${args.join("|")}]`;

test("register returns a frozen record with name and handler", () => {
  const registry = new CommandRegistry();
  const handler = tag("a");
  const record: Command = registry.register("alpha", handler);
  assert.strictEqual(record.name, "alpha");
  same(record.handler, handler);
  assert.ok(Object.isFrozen(record));
});

test("get returns the same record every time", () => {
  const registry = new CommandRegistry();
  const record = registry.register("beta", tag("b"));
  same(registry.get("beta"), record);
  same(registry.get("beta"), registry.get("beta"));
});

test("run passes arguments and returns the handler result", () => {
  const registry = new CommandRegistry();
  const seen: (readonly string[])[] = [];
  registry.register("gamma", (args) => {
    seen.push(args);
    return `n=${args.length}`;
  });
  assert.strictEqual(registry.run("gamma", ["p", "q"]), "n=2");
  assert.strictEqual(registry.run("gamma"), "n=0");
  assert.deepStrictEqual(seen.map((a) => [...a]), [["p", "q"], []]);
});

test("has is true only for registered names", () => {
  const registry = new CommandRegistry();
  registry.register("delta", tag("d"));
  assert.strictEqual(registry.has("delta"), true);
  assert.strictEqual(registry.has("Delta"), false);
  assert.strictEqual(registry.has("delt"), false);
});

test("unknown names: get, has and run", () => {
  const registry = new CommandRegistry();
  registry.register("eps", tag("e"));
  same(registry.get("zeta"), undefined);
  assert.strictEqual(registry.has("zeta"), false);
  const err = thrown(() => registry.run("zeta", ["1"]));
  assert.ok(err instanceof UnknownCommandError);
  assert.ok(err instanceof Error);
  const e = err as UnknownCommandError;
  assert.strictEqual(e.name, "UnknownCommandError");
  assert.strictEqual(e.commandName, "zeta");
  assert.strictEqual(e.message, "Unknown command: zeta");
});

test("duplicate registration error details", () => {
  const registry = new CommandRegistry();
  const first = registry.register("eta", tag("first"));
  const err = thrown(() => registry.register("eta", tag("second")));
  assert.ok(err instanceof DuplicateCommandError);
  assert.ok(err instanceof Error);
  const e = err as DuplicateCommandError;
  assert.strictEqual(e.name, "DuplicateCommandError");
  assert.strictEqual(e.commandName, "eta");
  assert.strictEqual(e.message, "Command already registered: eta");
  same(registry.get("eta"), first);
  assert.strictEqual(registry.run("eta", ["z"]), "first[z]");
  sameList(registry.list(), [first]);
});

test("list keeps registration order and returns a new array", () => {
  const registry = new CommandRegistry();
  const names = ["theta", "iota", "kappa", "lambda", "mu"];
  const records = names.map((n) => registry.register(n, tag(n)));
  const listed = registry.list();
  assert.strictEqual(listed.length, records.length);
  records.forEach((r, i) => same(listed[i], r));
  listed.reverse();
  listed.pop();
  assert.deepStrictEqual(registry.list().map((c) => c.name), names);
  assert.ok(registry.list() !== registry.list(), "list returns a new array");
});

test("registry with no commands", () => {
  const registry = new CommandRegistry();
  sameList(registry.list(), []);
  same(registry.get("anything"), undefined);
  assert.strictEqual(registry.has("anything"), false);
  assert.ok(thrown(() => registry.run("anything")) instanceof UnknownCommandError);
});

test("registries are independent", () => {
  const one = new CommandRegistry();
  const two = new CommandRegistry();
  one.register("nu", tag("1"));
  assert.strictEqual(two.has("nu"), false);
  two.register("nu", tag("2"));
  assert.strictEqual(one.run("nu"), "1[]");
  assert.strictEqual(two.run("nu"), "2[]");
});

test("name matching is exact", () => {
  const registry = new CommandRegistry();
  const lower = registry.register("xi", tag("lower"));
  const upper = registry.register("XI", tag("upper"));
  const spaced = registry.register(" xi", tag("spaced"));
  same(registry.get("xi"), lower);
  same(registry.get("XI"), upper);
  same(registry.get(" xi"), spaced);
  sameList(registry.list(), [lower, upper, spaced]);
});

test("public exports and method parameter counts", () => {
  assert.strictEqual(typeof api.CommandRegistry, "function");
  assert.ok(api.DuplicateCommandError.prototype instanceof Error);
  assert.ok(api.UnknownCommandError.prototype instanceof Error);
  const registry = new CommandRegistry();
  assert.strictEqual(registry.register.length, 2);
  assert.strictEqual(registry.get.length, 1);
  assert.strictEqual(registry.has.length, 1);
  assert.strictEqual(registry.list.length, 0);
  assert.strictEqual(typeof registry.run, "function");
});

test("handlers are called as given", () => {
  const registry = new CommandRegistry();
  let calls = 0;
  const handler: CommandHandler = () => `call ${++calls}`;
  registry.register("omicron", handler);
  same(registry.get("omicron")?.handler, handler);
  assert.strictEqual(registry.run("omicron"), "call 1");
  assert.strictEqual(registry.run("omicron"), "call 2");
  assert.strictEqual(calls, 2);
});
