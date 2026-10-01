#!/usr/bin/env node
"use strict";
const fs = require("fs");
const path = require("path");
const ts = require(path.join(process.cwd(), "node_modules", "typescript"));

function fail(msg) {
  process.stderr.write("STRUCTURAL FAIL: " + msg + "\n");
  process.exit(1);
}

function parse(relFile) {
  const full = path.join(process.cwd(), relFile);
  if (!fs.existsSync(full)) fail(`missing file: ${relFile}`);
  const text = fs.readFileSync(full, "utf8");
  return ts.createSourceFile(relFile, text, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TS);
}

function isExported(node) {
  const mods = ts.canHaveModifiers(node) ? ts.getModifiers(node) : undefined;
  return !!(mods && mods.some(m => m.kind === ts.SyntaxKind.ExportKeyword));
}

// 1. src/normalize.ts must export a function or const named normalizeField.
const normSrc = parse("src/normalize.ts");
let exportsNormalizeField = false;
ts.forEachChild(normSrc, node => {
  if (ts.isFunctionDeclaration(node) && node.name && node.name.text === "normalizeField"
      && isExported(node)) {
    exportsNormalizeField = true;
  }
  if (ts.isVariableStatement(node) && isExported(node)) {
    for (const decl of node.declarationList.declarations) {
      if (ts.isIdentifier(decl.name) && decl.name.text === "normalizeField") {
        exportsNormalizeField = true;
      }
    }
  }
});
if (!exportsNormalizeField) fail("src/normalize.ts does not export normalizeField");

// 2. Each exporter file: imports normalizeField from "./normalize", calls it at least once,
//    and no longer declares its own old per-file helper.
const exporters = [
  { file: "src/csv.ts", oldHelper: "cleanCsvValue" },
  { file: "src/json.ts", oldHelper: "cleanJsonValue" },
  { file: "src/markdown.ts", oldHelper: "cleanMdValue" },
];

for (const { file, oldHelper } of exporters) {
  const sf = parse(file);
  let hasImport = false, hasCall = false, hasOldHelper = false;

  function visit(node) {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)
        && node.moduleSpecifier.text === "./normalize") {
      const clause = node.importClause;
      if (clause && clause.namedBindings && ts.isNamedImports(clause.namedBindings)) {
        for (const el of clause.namedBindings.elements) {
          if (el.name.text === "normalizeField") hasImport = true;
        }
      }
    }
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)
        && node.expression.text === "normalizeField") {
      hasCall = true;
    }
    if (ts.isFunctionDeclaration(node) && node.name && node.name.text === oldHelper) {
      hasOldHelper = true;
    }
    if (ts.isVariableStatement(node)) {
      for (const decl of node.declarationList.declarations) {
        if (ts.isIdentifier(decl.name) && decl.name.text === oldHelper) hasOldHelper = true;
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sf);

  if (!hasImport) fail(`${file}: no "import { normalizeField } from './normalize'"`);
  if (!hasCall) fail(`${file}: normalizeField is never called`);
  if (hasOldHelper) fail(`${file}: old helper ${oldHelper} is still declared`);
}

process.stdout.write("STRUCTURAL OK\n");
process.exit(0);
