// node --test runs this file in a child process; it also spawns a grandchild.
import test from "node:test";
import assert from "node:assert";
import { execFileSync } from "node:child_process";
test("child process works in the evaluator sandbox", () => {
  assert.strictEqual(execFileSync(process.execPath, ["-e", "process.stdout.write('kid')"]).toString(), "kid");
});
