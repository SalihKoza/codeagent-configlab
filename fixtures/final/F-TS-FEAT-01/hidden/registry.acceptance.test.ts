// Acceptance: command aliases (statement "New feature", "Name rules", "Errors").
import { test } from "node:test";
import assert from "node:assert/strict";
import * as api from "../src/index";
import { Command, CommandRegistry, DuplicateCommandError, UnknownCommandError } from "../src/index";

// The new API is reached through these helpers so that this file also compiles against a
// registry without aliases; there, the presence assertions fail.
interface WithAliases {
  addAlias(alias: string, commandName: string): void;
}
type ConflictError = Error & { readonly conflictName: string; readonly existing: string };

function aliasApi(registry: CommandRegistry): WithAliases {
  const method = (registry as unknown as Record<string, unknown>).addAlias;
  assert.strictEqual(typeof method, "function", "CommandRegistry has an addAlias method");
  return registry as unknown as WithAliases;
}

function addAlias(registry: CommandRegistry, alias: string, commandName: string): void {
  aliasApi(registry).addAlias(alias, commandName);
}

function conflictClass(): Function {
  const cls = (api as unknown as Record<string, unknown>).NameConflictError;
  assert.strictEqual(typeof cls, "function", "NameConflictError is exported");
  return cls as Function;
}

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

function assertConflict(err: unknown, name: string, existing: "command" | "alias"): void {
  assert.ok(err instanceof conflictClass(), `NameConflictError expected, got ${String(err)}`);
  const e = err as ConflictError;
  assert.ok(e instanceof Error);
  assert.strictEqual(e.name, "NameConflictError");
  assert.strictEqual(e.conflictName, name);
  assert.strictEqual(e.existing, existing);
  const holder = existing === "command" ? "a command" : "an alias";
  assert.strictEqual(e.message, `Name already in use by ${holder}: ${name}`);
}

function assertUnknown(err: unknown, name: string): void {
  assert.ok(err instanceof UnknownCommandError, `UnknownCommandError expected, got ${String(err)}`);
  assert.strictEqual((err as UnknownCommandError).commandName, name);
  assert.strictEqual((err as UnknownCommandError).message, `Unknown command: ${name}`);
}

function snapshot(registry: CommandRegistry, names: string[]): unknown[] {
  return [registry.list(), names.map((n) => registry.get(n))];
}

const tag = (label: string) => (args: readonly string[]) => `${label}(${args.join(",")})`;

test("alias API is exported", () => {
  const registry = new CommandRegistry();
  const method = (aliasApi(registry) as unknown as { addAlias: Function }).addAlias;
  assert.strictEqual(method.length, 2);
  assert.ok(conflictClass().prototype instanceof Error);
});

test("an alias resolves through get, has and run", () => {
  const registry = new CommandRegistry();
  const record = registry.register("status", tag("status"));
  const result = (aliasApi(registry).addAlias as Function).call(registry, "st", "status");
  assert.strictEqual(result, undefined);
  same(registry.get("st"), record);
  assert.strictEqual(registry.has("st"), true);
  assert.strictEqual(registry.run("st", ["-s"]), "status(-s)");
  assert.strictEqual(registry.run("st"), registry.run("status"));
});

test("alias lookup returns the canonical record itself", () => {
  const registry = new CommandRegistry();
  const handler = tag("deploy");
  const record = registry.register("deploy", handler);
  addAlias(registry, "ship", "deploy");
  const viaAlias = registry.get("ship") as Command;
  same(viaAlias, registry.get("deploy"));
  same(viaAlias, record);
  assert.strictEqual(viaAlias.name, "deploy");
  same(viaAlias.handler, handler);
});

test("several aliases for one command", () => {
  const registry = new CommandRegistry();
  const record = registry.register("remove", tag("remove"));
  addAlias(registry, "rm", "remove");
  addAlias(registry, "del", "remove");
  addAlias(registry, "erase", "remove");
  for (const alias of ["rm", "del", "erase"]) {
    same(registry.get(alias), record);
    assert.strictEqual(registry.run(alias, [alias]), `remove(${alias})`);
  }
});

test("aliases for several commands resolve to their own command", () => {
  const registry = new CommandRegistry();
  const a = registry.register("fetch", tag("fetch"));
  const b = registry.register("merge", tag("merge"));
  addAlias(registry, "f", "fetch");
  addAlias(registry, "m", "merge");
  addAlias(registry, "get", "fetch");
  same(registry.get("f"), a);
  same(registry.get("get"), a);
  same(registry.get("m"), b);
  assert.strictEqual(registry.run("m", ["x"]), "merge(x)");
});

test("list excludes aliases and keeps registration order", () => {
  const registry = new CommandRegistry();
  const one = registry.register("one", tag("1"));
  const two = registry.register("two", tag("2"));
  const three = registry.register("three", tag("3"));
  addAlias(registry, "3", "three");
  addAlias(registry, "1", "one");
  addAlias(registry, "uno", "one");
  const listed = registry.list();
  assert.strictEqual(listed.length, 3);
  same(listed[0], one);
  same(listed[1], two);
  same(listed[2], three);
});

test("canonical lookup is unchanged after aliases are added", () => {
  const registry = new CommandRegistry();
  const record = registry.register("lint", tag("lint"));
  addAlias(registry, "l", "lint");
  same(registry.get("lint"), record);
  assert.strictEqual(registry.has("lint"), true);
  assert.strictEqual(registry.run("lint", ["src"]), "lint(src)");
});

test("alias equal to another command name is rejected", () => {
  const registry = new CommandRegistry();
  const pull = registry.register("pull", tag("pull"));
  registry.register("push", tag("push"));
  const err = thrown(() => addAlias(registry, "pull", "push"));
  assertConflict(err, "pull", "command");
  same(registry.get("pull"), pull);
  assert.strictEqual(registry.run("pull"), "pull()");
});

test("alias equal to its own target is rejected", () => {
  const registry = new CommandRegistry();
  const record = registry.register("init", tag("init"));
  const err = thrown(() => addAlias(registry, "init", "init"));
  assertConflict(err, "init", "command");
  same(registry.get("init"), record);
  sameList(registry.list(), [record]);
});

test("alias already used for another command is rejected", () => {
  const registry = new CommandRegistry();
  const show = registry.register("show", tag("show"));
  registry.register("stash", tag("stash"));
  addAlias(registry, "s", "show");
  const err = thrown(() => addAlias(registry, "s", "stash"));
  assertConflict(err, "s", "alias");
  same(registry.get("s"), show);
});

test("adding the same alias twice is rejected", () => {
  const registry = new CommandRegistry();
  const record = registry.register("clone", tag("clone"));
  addAlias(registry, "cl", "clone");
  const err = thrown(() => addAlias(registry, "cl", "clone"));
  assertConflict(err, "cl", "alias");
  same(registry.get("cl"), record);
});

test("alias for an unknown command is rejected", () => {
  const registry = new CommandRegistry();
  registry.register("tag", tag("tag"));
  const err = thrown(() => addAlias(registry, "t", "tags"));
  assertUnknown(err, "tags");
  assert.strictEqual(registry.has("t"), false);
  same(registry.get("t"), undefined);
});

test("alias that targets another alias is rejected", () => {
  const registry = new CommandRegistry();
  const record = registry.register("checkout", tag("checkout"));
  addAlias(registry, "co", "checkout");
  const err = thrown(() => addAlias(registry, "c", "co"));
  assertUnknown(err, "co");
  assert.strictEqual(registry.has("c"), false);
  same(registry.get("co"), record);
});

test("registering a command under an alias name is rejected", () => {
  const registry = new CommandRegistry();
  const log = registry.register("log", tag("log"));
  addAlias(registry, "history", "log");
  const err = thrown(() => registry.register("history", tag("history")));
  assertConflict(err, "history", "alias");
  same(registry.get("history"), log);
  assert.strictEqual(registry.run("history", ["1"]), "log(1)");
  sameList(registry.list(), [log]);
});

test("an unknown target is reported before a taken alias name", () => {
  const registry = new CommandRegistry();
  registry.register("build", tag("build"));
  addAlias(registry, "b", "build");
  assertUnknown(thrown(() => addAlias(registry, "b", "nothing")), "nothing");
  assertUnknown(thrown(() => addAlias(registry, "build", "nothing")), "nothing");
  assertUnknown(thrown(() => addAlias(registry, "b", "b")), "b");
});

test("rejected alias calls leave the registry unchanged", () => {
  const registry = new CommandRegistry();
  registry.register("open", tag("open"));
  registry.register("close", tag("close"));
  addAlias(registry, "o", "open");
  const names = ["open", "close", "o", "c", "x"];
  const before = snapshot(registry, names);
  thrown(() => addAlias(registry, "o", "close"));
  thrown(() => addAlias(registry, "close", "open"));
  thrown(() => addAlias(registry, "x", "missing"));
  thrown(() => addAlias(registry, "c", "o"));
  thrown(() => registry.register("o", tag("other")));
  const after = snapshot(registry, names);
  sameList(after[0] as unknown[], before[0] as unknown[], "list");
  sameList(after[1] as unknown[], before[1] as unknown[], "lookups");
  const x = registry.register("x", tag("x"));
  same(registry.get("x"), x);
});

test("duplicate command registration is unchanged when aliases exist", () => {
  const registry = new CommandRegistry();
  const record = registry.register("sync", tag("sync"));
  addAlias(registry, "sy", "sync");
  const err = thrown(() => registry.register("sync", tag("again")));
  assert.ok(err instanceof DuplicateCommandError);
  assert.strictEqual((err as DuplicateCommandError).commandName, "sync");
  assert.strictEqual((err as DuplicateCommandError).message, "Command already registered: sync");
  same(registry.get("sync"), record);
  same(registry.get("sy"), record);
});

test("commands registered after aliases are listed after earlier commands", () => {
  const registry = new CommandRegistry();
  const first = registry.register("first", tag("first"));
  addAlias(registry, "f1", "first");
  const second = registry.register("second", tag("second"));
  addAlias(registry, "s2", "second");
  addAlias(registry, "f2", "first");
  const third = registry.register("third", tag("third"));
  sameList(registry.list(), [first, second, third]);
  same(registry.get("f2"), first);
  same(registry.get("s2"), second);
});

test("names unrelated to any example", () => {
  const registry = new CommandRegistry();
  const q = registry.register("zq-7", tag("zq"));
  const w = registry.register("w.9", tag("w"));
  addAlias(registry, "Alpha_1", "zq-7");
  addAlias(registry, "k k", "w.9");
  same(registry.get("Alpha_1"), q);
  assert.strictEqual(registry.run("k k", ["v"]), "w(v)");
  assertConflict(thrown(() => addAlias(registry, "Alpha_1", "w.9")), "Alpha_1", "alias");
  assertConflict(thrown(() => registry.register("k k", tag("n"))), "k k", "alias");
  sameList(registry.list(), [q, w]);
});

test("aliases do not change command records", () => {
  const registry = new CommandRegistry();
  const handler = tag("diff");
  const record = registry.register("diff", handler);
  addAlias(registry, "d", "diff");
  addAlias(registry, "changes", "diff");
  assert.ok(Object.isFrozen(record));
  same(registry.get("diff"), record);
  assert.strictEqual(record.name, "diff");
  same(record.handler, handler);
});
