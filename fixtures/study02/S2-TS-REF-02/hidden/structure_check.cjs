"use strict";
/*
 * Structural check for S2-TS-REF-02 (extract a shared EvictionPolicy / isExpired helper).
 *
 * Usage: node structure_check.cjs [ROOT] (ROOT defaults to the current directory).
 * Parses ROOT/src/store.ts with the TypeScript compiler API (no execution of candidate code).
 * Prints {"ok": bool, "rules": {R1, R2: {"ok", "detail"}}}. Exit 0 = both rules hold, 1 = at
 * least one fails, 3 = internal error of this checker.
 *
 * R1 (shared helper exists and is used by both call sites): a function/const declared in
 *    store.ts, other than `seen`/`purgeExpired` themselves, is called from inside BOTH `seen`'s
 *    body and `purgeExpired`'s body.
 * R2 (no re-duplicated inline comparison): neither `seen` nor `purgeExpired`'s own body contains
 *    a direct relational comparison (>, >=, <, <=) — that logic must live only in the extracted
 *    helper, not be re-inlined at either call site.
 */
const path = require("path");
const fs = require("fs");

function findFunctionLike(ts, sourceFile, name) {
  let found;
  function visit(node) {
    if (found) return;
    if (ts.isFunctionDeclaration(node) && node.name && node.name.text === name) { found = node; return; }
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === name
      && node.initializer && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))) {
      found = node.initializer; return;
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return found;
}

function calledNames(ts, fnNode) {
  const names = new Set();
  function visit(node) {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)) names.add(node.expression.text);
    ts.forEachChild(node, visit);
  }
  if (fnNode.body) ts.forEachChild(fnNode.body, visit);
  return names;
}

function hasDirectComparison(ts, fnNode) {
  let found = false;
  const RELOPS = new Set([
    ts.SyntaxKind.GreaterThanToken, ts.SyntaxKind.GreaterThanEqualsToken,
    ts.SyntaxKind.LessThanToken, ts.SyntaxKind.LessThanEqualsToken,
  ]);
  function visit(node) {
    if (found) return;
    if (ts.isBinaryExpression(node) && RELOPS.has(node.operatorToken.kind)) { found = true; return; }
    ts.forEachChild(node, visit);
  }
  if (fnNode.body) ts.forEachChild(fnNode.body, visit);
  return found;
}

function declaredLocalNames(ts, sourceFile) {
  const names = new Set();
  function visit(node) {
    if (ts.isFunctionDeclaration(node) && node.name) names.add(node.name.text);
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) names.add(node.name.text);
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return names;
}

function analyse(root, ts) {
  const rules = {};
  const set = (r, ok, detail) => { rules[r] = { ok: Boolean(ok), detail }; };
  const storePath = path.join(root, "src", "store.ts");
  const text = fs.readFileSync(storePath, "utf8");
  const sourceFile = ts.createSourceFile(storePath, text, ts.ScriptTarget.ES2022, true);

  const seenFn = findFunctionLike(ts, sourceFile, "seen");
  const purgeFn = findFunctionLike(ts, sourceFile, "purgeExpired");
  if (!seenFn || !purgeFn) {
    set("R1", false, "could not locate seen() and/or purgeExpired() in src/store.ts");
    set("R2", false, "could not locate seen() and/or purgeExpired() in src/store.ts");
    return rules;
  }

  const localNames = declaredLocalNames(ts, sourceFile);
  const seenCalls = calledNames(ts, seenFn);
  const purgeCalls = calledNames(ts, purgeFn);
  const shared = [...seenCalls].filter((n) => purgeCalls.has(n) && localNames.has(n)
    && n !== "seen" && n !== "purgeExpired");
  set("R1", shared.length > 0, shared.length
    ? `shared helper(s) called by both: ${shared.join(", ")}`
    : "no locally-declared function is called from both seen() and purgeExpired()");

  const seenInline = hasDirectComparison(ts, seenFn);
  const purgeInline = hasDirectComparison(ts, purgeFn);
  set("R2", !seenInline && !purgeInline,
    (seenInline ? "seen() still contains a direct relational comparison; " : "")
    + (purgeInline ? "purgeExpired() still contains a direct relational comparison" : "")
    || "neither function re-implements the comparison inline");

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
