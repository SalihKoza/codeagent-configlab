import { test } from "node:test";
import assert from "node:assert/strict";
import { CommandRegistry, DuplicateCommandError, UnknownCommandError } from "../src/index";

function thrown(fn: () => unknown): unknown {
  try {
    fn();
  } catch (err) {
    return err;
  }
  assert.ok(false, "expected an error to be thrown");
  return undefined;
}

const echo = (args: readonly string[]) => args.join(" ");

test("register returns the command record", () => {
  const registry = new CommandRegistry();
  const command = registry.register("echo", echo);
  assert.strictEqual(command.name, "echo");
  assert.strictEqual(command.handler, echo);
  assert.strictEqual(registry.get("echo"), command);
});

test("run passes the arguments to the handler", () => {
  const registry = new CommandRegistry();
  registry.register("echo", echo);
  assert.strictEqual(registry.run("echo", ["a", "b"]), "a b");
  assert.strictEqual(registry.run("echo"), "");
});

test("has reports registered names", () => {
  const registry = new CommandRegistry();
  registry.register("echo", echo);
  assert.strictEqual(registry.has("echo"), true);
  assert.strictEqual(registry.has("other"), false);
});

test("list returns commands in registration order", () => {
  const registry = new CommandRegistry();
  registry.register("start", () => "started");
  registry.register("stop", () => "stopped");
  assert.deepStrictEqual(
    registry.list().map((c) => c.name),
    ["start", "stop"],
  );
});

test("registering a name twice raises DuplicateCommandError", () => {
  const registry = new CommandRegistry();
  registry.register("echo", echo);
  const err = thrown(() => registry.register("echo", () => "again"));
  assert.ok(err instanceof DuplicateCommandError);
  assert.strictEqual((err as DuplicateCommandError).commandName, "echo");
  assert.strictEqual(registry.run("echo", ["x"]), "x");
});

test("running an unknown name raises UnknownCommandError", () => {
  const registry = new CommandRegistry();
  const err = thrown(() => registry.run("missing"));
  assert.ok(err instanceof UnknownCommandError);
  assert.strictEqual((err as UnknownCommandError).commandName, "missing");
  assert.strictEqual(registry.get("missing"), undefined);
});

test("an empty registry lists nothing", () => {
  assert.deepStrictEqual(new CommandRegistry().list(), []);
});
