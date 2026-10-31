"use strict";
/*
 * Structural check for S2-TS-REF-01 (extract pending-job ordering into a dedicated abstraction).
 *
 * Usage: node structure_check.cjs [ROOT] (ROOT defaults to the current directory).
 * Parses ROOT/src/ordering.ts and ROOT/src/index.ts with the TypeScript compiler API (no
 * execution of candidate code). Prints {"ok": bool, "rules": {R1, R2: {"ok", "detail"}}}.
 * Exit 0 = both rules hold, 1 = at least one fails, 3 = internal error of this checker.
 *
 * R1 (encapsulated ordering type exists): ordering.ts declares a class (any name) with at least
 *    two methods, one of which inserts (visits a push/unshift/splice-style array mutation or a
 *    sort call in its body) and one of which removes-and-returns (visits a shift/pop/splice-style
 *    mutation in its body).
 * R2 (index.ts delegates, does not manipulate a raw array itself): index.ts's source text does
 *    not call `.sort(`, `.push(`, or `.shift(` directly (those calls must live inside the R1
 *    class in ordering.ts, not in index.ts).
 */
const path = require("path");
const fs = require("fs");

function findClasses(ts, sourceFile) {
  const classes = [];
  function visit(node) {
    if (ts.isClassDeclaration(node)) classes.push(node);
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return classes;
}

function methodBodiesContainCall(ts, classNode, methodNames) {
  const found = new Set();
  for (const member of classNode.members) {
    if (!ts.isMethodDeclaration(member) || !member.body) continue;
    let hit = false;
    function visit(node) {
      if (hit) return;
      if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
        && methodNames.includes(node.expression.name.text)) hit = true;
      ts.forEachChild(node, visit);
    }
    visit(member.body);
    if (hit) found.add(member.name && member.name.getText());
  }
  return found;
}

function analyse(root, ts) {
  const rules = {};
  const set = (r, ok, detail) => { rules[r] = { ok: Boolean(ok), detail }; };

  const orderingPath = path.join(root, "src", "ordering.ts");
  const orderingText = fs.readFileSync(orderingPath, "utf8");
  const orderingSf = ts.createSourceFile(orderingPath, orderingText, ts.ScriptTarget.ES2022, true);

  const classes = findClasses(ts, orderingSf);
  let r1ok = false;
  let r1detail = "no class declaration found in src/ordering.ts";
  for (const cls of classes) {
    const inserters = methodBodiesContainCall(ts, cls, ["push", "unshift", "sort", "splice"]);
    const removers = methodBodiesContainCall(ts, cls, ["shift", "pop", "splice"]);
    if (inserters.size > 0 && removers.size > 0) {
      r1ok = true;
      r1detail = `class ${cls.name ? cls.name.text : "<anonymous>"} has an insert-like method `
        + `(${[...inserters].join(",")}) and a remove-like method (${[...removers].join(",")})`;
      break;
    }
  }
  set("R1", r1ok, r1detail);

  const indexPath = path.join(root, "src", "index.ts");
  const indexText = fs.readFileSync(indexPath, "utf8");
  const forbidden = [".sort(", ".push(", ".shift("];
  const hits = forbidden.filter((f) => indexText.includes(f));
  set("R2", hits.length === 0, hits.length
    ? `index.ts still calls ${hits.join(", ")} directly instead of delegating to ordering.ts`
    : "index.ts does not manipulate a raw array directly");

  return rules;
}

function main() {
  const root = path.resolve(process.argv[2] || ".");
  let rules;
  try {
    const ts = require(path.join(root, "node_modules", "typescript"));
    rules = analyse(root, ts);
  } catch (exc) {
    process.stdout.write(JSON.stringify({ internal_error: `${exc && exc.name}: ${exc && exc.message}` }) + "\n");
    return 3;
  }
  const RULES = ["R1", "R2"];
  const ordered = {};
  for (const r of RULES) ordered[r] = rules[r] || { ok: false, detail: "not evaluated" };
  const ok = RULES.every((r) => ordered[r].ok);
  process.stdout.write(JSON.stringify({ ok, rules: ordered }, null, 1) + "\n");
  return ok ? 0 : 1;
}

process.exitCode = main();
