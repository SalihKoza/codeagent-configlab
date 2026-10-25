"use strict";
/*
 * Structural check for the required handler-registry dispatch (rules S1-S6 of the task statement).
 *
 * Usage: node structure_check.cjs [ROOT]   (ROOT defaults to the current directory)
 * Analyses every ROOT/src/**\/*.ts (not .d.ts) with the TypeScript compiler API (program + type
 * checker, symbols resolved through imports/aliases). Nothing is executed or imported from the
 * candidate, and no text matching is used. TypeScript is loaded from ROOT/node_modules/typescript.
 * Prints {"ok": bool, "rules": {S1..S6: {"ok", "detail"}}}. Exit 0 = every rule holds, 1 = at least
 * one rule fails, 3 = internal error of this checker.
 *
 * Definitions (as stated publicly):
 * - op identifiers: receive, ship, adjust, count, report.
 * - registry: the variable `opHandlers` exported from src/handlers.ts.
 * - registry entry: an op identifier written as a literal (identifier or string key of an object
 *   literal property/method, string literal call argument or first element of a two-element array
 *   literal) together with its handler (the property value / the next argument / the second
 *   element), found (a) inside the registry's initializer or inside a src function called from it
 *   (transitively),
 *   or (b) in `opHandlers.set(k, h)` / `opHandlers[k] = h` / `opHandlers.k = h`, or (c) in a call of
 *   a src function whose body performs (b) with two of its parameters.
 * - handler: resolves to a function, a class instance (`new C(...)`; its class methods) or an object
 *   literal with a `handle` member.
 * - reaches: code reaches a function/method/variable/class when it mentions it (identifier or
 *   property name resolved by the type checker), transitively; classes contribute all members and
 *   their base classes; variables contribute their initializer. Only declarations in src count.
 * - dispatch path: processRequest (resolved from src/index.ts) plus everything it reaches, without
 *   following the registry itself.
 * - op-derived value: request.op (or request["op"]) of processRequest's first parameter, a variable
 *   or destructured binding initialized from one, a parameter of a src function called with one.
 * - dispatcher: a src function containing a switch with two or more op-identifier case labels, or
 *   equality comparisons against two or more distinct op identifiers. The dispatch path must not
 *   reach one (S4) and no handler may reach one (S5).
 */
const path = require("path");
const fs = require("fs");

const OPS = ["receive", "ship", "adjust", "count", "report"];
const REGISTRY = "opHandlers";
const REGISTRY_MODULE = "src/handlers.ts";
const ENTRY = "processRequest";
const INDEX = "src/index.ts";
const LEDGER_STATE = new Set(["stock", "journal"]);
const BEHAVIOR_ERRORS = new Set(["ParamError", "ShortageError"]);
const MEMBERSHIP = new Set(["includes", "indexOf", "lastIndexOf", "has", "get", "find", "findIndex", "some"]);
const RULES = ["S1", "S2", "S3", "S4", "S5", "S6"];

function listSources(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const name of fs.readdirSync(dir).sort()) {
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) out.push(...listSources(p));
    else if (name.endsWith(".ts") && !name.endsWith(".d.ts")) out.push(p);
  }
  return out;
}

function analyse(root, ts) {
  const rules = {};
  const set = (r, ok, detail) => { rules[r] = { ok: Boolean(ok), detail }; };
  const files = listSources(path.join(root, "src"));
  const program = ts.createProgram(files, {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true,
    skipLibCheck: true, noEmit: true,
  });
  const checker = program.getTypeChecker();
  const srcFiles = new Set(files.map((f) => path.resolve(f)));
  const inSrc = (node) => srcFiles.has(path.resolve(node.getSourceFile().fileName));
  const rel = (node) => path.relative(root, node.getSourceFile().fileName).split(path.sep).join("/");
  const where = (node) => {
    const sf = node.getSourceFile();
    return `${rel(node)}:${sf.getLineAndCharacterOfPosition(node.getStart()).line + 1}`;
  };
  const sourceFile = (relPath) => program.getSourceFile(path.join(root, relPath))
    || program.getSourceFiles().find((sf) => path.resolve(sf.fileName) === path.resolve(root, relPath));

  const resolveSym = (sym) => {
    let s = sym;
    for (let i = 0; s && (s.flags & ts.SymbolFlags.Alias) && i < 10; i++) s = checker.getAliasedSymbol(s);
    return s ? checker.getExportSymbolOfSymbol(s) : s;
  };
  const symAt = (node) => {
    // A shorthand property `{ receive }` mentions the value `receive`, not the new property.
    const s = node.parent && ts.isShorthandPropertyAssignment(node.parent) && node.parent.name === node
      ? checker.getShorthandAssignmentValueSymbol(node.parent)
      : checker.getSymbolAtLocation(node);
    return resolveSym(s);
  };
  const unwrap = (e) => {
    while (e && (ts.isParenthesizedExpression(e) || ts.isAsExpression(e) || ts.isNonNullExpression(e)
      || ts.isTypeAssertionExpression(e) || (ts.isSatisfiesExpression && ts.isSatisfiesExpression(e)))) e = e.expression;
    return e;
  };
  const literalText = (n) => {
    n = unwrap(n);
    if (!n) return undefined;
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) return n.text;
    return undefined;
  };
  const keyText = (name) => {
    if (!name) return undefined;
    if (ts.isIdentifier(name) || ts.isStringLiteral(name)) return name.text;
    if (ts.isComputedPropertyName(name)) return literalText(name.expression);
    return undefined;
  };
  const isFunctionLike = (n) => ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n)
    || ts.isArrowFunction(n) || ts.isMethodDeclaration(n) || ts.isConstructorDeclaration(n)
    || ts.isGetAccessorDeclaration(n) || ts.isSetAccessorDeclaration(n);
  const inTypePosition = (n) => {
    for (let p = n.parent; p; p = p.parent) {
      if (ts.isTypeNode(p) || ts.isHeritageClause(p) && p.token === ts.SyntaxKind.ImplementsKeyword) return true;
      if (ts.isStatement(p) || isFunctionLike(p)) return false;
    }
    return false;
  };
  const walk = (node, fn) => { fn(node); ts.forEachChild(node, (c) => walk(c, fn)); };
  const EQ = new Set([ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken,
    ts.SyntaxKind.EqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken, ts.SyntaxKind.LessThanToken,
    ts.SyntaxKind.GreaterThanToken, ts.SyntaxKind.LessThanEqualsToken, ts.SyntaxKind.GreaterThanEqualsToken]);

  // ---- anchors -------------------------------------------------------------------------------
  const handlersSf = sourceFile(REGISTRY_MODULE);
  let registryDecl = null;
  let registrySym = null;
  if (handlersSf) {
    const modSym = checker.getSymbolAtLocation(handlersSf);
    const exported = modSym ? checker.getExportsOfModule(modSym) : [];
    const exp = exported.find((s) => s.name === REGISTRY);
    if (exp) {
      registrySym = resolveSym(exp);
      registryDecl = (registrySym.declarations || []).find((d) => ts.isVariableDeclaration(d)
        && d.getSourceFile() === handlersSf) || null;
    }
  }
  const isRegistry = (expr) => {
    expr = unwrap(expr);
    return Boolean(registrySym && expr && ts.isIdentifier(expr) && symAt(expr) === registrySym);
  };
  set("S1", registryDecl, registryDecl
    ? `${REGISTRY} is an exported variable of ${REGISTRY_MODULE} (${where(registryDecl)})`
    : handlersSf ? `${REGISTRY_MODULE} does not export a variable named ${REGISTRY}`
      : `${REGISTRY_MODULE} does not exist`);

  let entryDecl = null;
  const indexSf = sourceFile(INDEX);
  if (indexSf) {
    const modSym = checker.getSymbolAtLocation(indexSf);
    const exp = modSym && checker.getExportsOfModule(modSym).find((s) => s.name === ENTRY);
    const target = exp && resolveSym(exp);
    entryDecl = target && (target.declarations || []).find((d) => ts.isFunctionDeclaration(d)
      || (ts.isVariableDeclaration(d) && d.initializer && isFunctionLike(unwrap(d.initializer)))) || null;
    if (entryDecl && ts.isVariableDeclaration(entryDecl)) entryDecl = unwrap(entryDecl.initializer);
  }

  // ---- reachability ---------------------------------------------------------------------------
  // Region roots are function-like nodes, variable initializers, class nodes or object literals.
  function targetsOfSymbol(sym) {
    const out = [];
    for (const d of (sym && sym.declarations) || []) {
      if (!inSrc(d)) continue;
      if (isFunctionLike(d)) out.push(d);
      else if (ts.isVariableDeclaration(d) && d.initializer) out.push(d.initializer);
      else if ((ts.isPropertyAssignment(d) || ts.isPropertyDeclaration(d)) && d.initializer) out.push(d.initializer);
      else if (ts.isClassDeclaration(d) || ts.isClassExpression(d)) out.push(d);
    }
    return out;
  }
  function region(roots, opts = {}) {
    const seen = new Set();
    const queue = [...roots];
    while (queue.length) {
      const r = queue.shift();
      if (!r || seen.has(r)) continue;
      seen.add(r);
      if (ts.isClassDeclaration(r) || ts.isClassExpression(r)) {
        for (const h of r.heritageClauses || []) {
          if (h.token !== ts.SyntaxKind.ExtendsKeyword) continue;
          for (const t of h.types) queue.push(...targetsOfSymbol(symAt(t.expression)));
        }
      }
      walk(r, (n) => {
        if (!ts.isIdentifier(n) || inTypePosition(n)) return;
        const p = n.parent;
        if (p && (ts.isImportSpecifier(p) || ts.isImportClause(p) || ts.isNamespaceImport(p))) return;
        const sym = symAt(n);
        if (!sym) return;
        if (opts.stopAtRegistry && sym === registrySym) return;
        for (const t of targetsOfSymbol(sym)) if (!seen.has(t)) queue.push(t);
      });
    }
    return seen;
  }
  const nodesOf = (roots) => {
    const out = [];
    for (const r of roots) walk(r, (n) => out.push(n));
    return out;
  };

  // ---- registry entries (S2) ------------------------------------------------------------------
  const entries = [];   // {op, handler: Expression|Node, at}
  const addEntry = (op, handler, at) => { if (OPS.includes(op) && handler) entries.push({ op, handler, at }); };
  function scanEntries(scopeNode) {
    walk(scopeNode, (n) => {
      if (ts.isPropertyAssignment(n) && ts.isObjectLiteralExpression(n.parent)) addEntry(keyText(n.name), n.initializer, n);
      else if (ts.isShorthandPropertyAssignment(n)) addEntry(n.name.text, n.name, n);
      else if (ts.isMethodDeclaration(n) && ts.isObjectLiteralExpression(n.parent)) addEntry(keyText(n.name), n, n);
      else if (ts.isArrayLiteralExpression(n) && n.elements.length === 2) addEntry(literalText(n.elements[0]), n.elements[1], n);
      else if (ts.isCallExpression(n)) {
        n.arguments.forEach((a, i) => { if (i + 1 < n.arguments.length) addEntry(literalText(a), n.arguments[i + 1], n); });
      }
    });
  }
  if (registryDecl) {
    if (registryDecl.initializer) {
      // (a) the initializer and every src function called from it (factories, builders), transitively
      const scopes = [registryDecl.initializer];
      const done = new Set();
      while (scopes.length) {
        const scope = scopes.shift();
        if (done.has(scope)) continue;
        done.add(scope);
        scanEntries(scope);
        walk(scope, (n) => {
          if (!ts.isCallExpression(n) || n === scope) return;
          for (const f of targetsOfSymbol(symAt(unwrap(n.expression)))) {
            const fn = unwrap(f);
            if (fn && isFunctionLike(fn) && fn.body) scopes.push(fn.body);
          }
        });
      }
    }
    // (b) direct mutations and (c) registration functions, anywhere in src
    const registrars = new Map();   // function node -> [keyParamIndex, valueParamIndex]
    const mutation = (n) => {
      if (ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) && n.expression.name.text === "set"
        && isRegistry(n.expression.expression) && n.arguments.length >= 2) return [n.arguments[0], n.arguments[1]];
      if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
        const l = unwrap(n.left);
        if (ts.isElementAccessExpression(l) && isRegistry(l.expression)) return [l.argumentExpression, n.right];
        if (ts.isPropertyAccessExpression(l) && isRegistry(l.expression)) return [l.name, n.right];
      }
      return null;
    };
    for (const sf of program.getSourceFiles()) {
      if (!srcFiles.has(path.resolve(sf.fileName))) continue;
      walk(sf, (n) => {
        const m = mutation(n);
        if (!m) return;
        const [k, v] = m;
        const kText = ts.isIdentifier(k) && ts.isPropertyAccessExpression(k.parent) ? k.text : literalText(k);
        if (kText !== undefined) { addEntry(kText, v, n); return; }
        let fn = n.parent;
        while (fn && !isFunctionLike(fn)) fn = fn.parent;
        if (!fn) return;
        const pIndex = (e) => fn.parameters.findIndex((p) => ts.isIdentifier(p.name) && ts.isIdentifier(unwrap(e))
          && symAt(unwrap(e)) === checker.getSymbolAtLocation(p.name));
        const ki = pIndex(k), vi = pIndex(v);
        if (ki >= 0 && vi >= 0) registrars.set(fn, [ki, vi]);
      });
    }
    for (const sf of program.getSourceFiles()) {
      if (!srcFiles.has(path.resolve(sf.fileName))) continue;
      walk(sf, (n) => {
        if (!ts.isCallExpression(n)) return;
        const callee = unwrap(n.expression);
        const sym = ts.isIdentifier(callee) || ts.isPropertyAccessExpression(callee) ? symAt(callee) : undefined;
        for (const t of targetsOfSymbol(sym)) {
          const fnNode = isFunctionLike(t) ? t : unwrap(t);
          const idx = registrars.get(fnNode);
          if (idx) addEntry(literalText(n.arguments[idx[0]]), n.arguments[idx[1]], n);
        }
      });
    }
  }
  function resolveHandler(expr, depth = 0) {
    if (!expr || depth > 6) return null;
    if (isFunctionLike(expr)) return [expr];
    const e = unwrap(expr);
    if (!e) return null;
    if (isFunctionLike(e)) return [e];
    if (ts.isIdentifier(e) || ts.isPropertyAccessExpression(e)) {
      const sym = symAt(e);
      const out = [];
      for (const d of (sym && sym.declarations) || []) {
        if (!inSrc(d)) continue;
        if (ts.isFunctionDeclaration(d) || ts.isMethodDeclaration(d)) out.push(d);
        else if ((ts.isVariableDeclaration(d) || ts.isPropertyAssignment(d) || ts.isPropertyDeclaration(d)) && d.initializer) {
          const r = resolveHandler(d.initializer, depth + 1);
          if (r) out.push(...r);
        }
      }
      return out.length ? out : null;
    }
    if (ts.isNewExpression(e)) {
      const sym = symAt(e.expression);
      const cls = ((sym && sym.declarations) || []).filter((d) => inSrc(d) && (ts.isClassDeclaration(d) || ts.isClassExpression(d)));
      return cls.length ? cls : null;
    }
    if (ts.isObjectLiteralExpression(e)) {
      const h = e.properties.find((p) => keyText(p.name) === "handle");
      if (!h) return null;
      return ts.isMethodDeclaration(h) ? [h] : ts.isPropertyAssignment(h) ? resolveHandler(h.initializer, depth + 1) : null;
    }
    if (ts.isCallExpression(e)) {   // a src factory returning a handler
      const out = [];
      for (const t of targetsOfSymbol(symAt(unwrap(e.expression)))) {
        if (!isFunctionLike(t)) continue;
        if (t.body && !ts.isBlock(t.body)) { const r = resolveHandler(t.body, depth + 1); if (r) out.push(...r); }
        walk(t, (n) => {
          if (ts.isReturnStatement(n) && n.expression) { const r = resolveHandler(n.expression, depth + 1); if (r) out.push(...r); }
        });
      }
      return out.length ? out : null;
    }
    return null;
  }
  const byOp = {};
  for (const op of OPS) byOp[op] = [];
  for (const e of entries) byOp[e.op].push({ ...e, roots: resolveHandler(e.handler) });
  const missing = OPS.filter((op) => !byOp[op].some((e) => e.roots));
  const unresolved = entries.filter((e) => !resolveHandler(e.handler)).map((e) => `${e.op}@${where(e.at)}`);
  set("S2", registryDecl && missing.length === 0,
    !registryDecl ? "no registry" : missing.length
      ? `no registry entry with a resolvable handler for: ${missing.join(", ")}`
        + (unresolved.length ? ` (unresolved entries: ${unresolved.join(", ")})` : "")
      : `entries: ${OPS.map((op) => `${op}@${where(byOp[op].find((x) => x.roots).at)}`).join(", ")}`);

  // ---- dispatchers: functions branching over two or more op identifiers -------------------------
  const dispatchers = new Set();
  for (const sf of program.getSourceFiles()) {
    if (!srcFiles.has(path.resolve(sf.fileName))) continue;
    walk(sf, (n) => {
      if (!isFunctionLike(n)) return;
      const seen = new Set();
      walk(n.body || n, (m) => {
        if (ts.isCaseClause(m) && OPS.includes(literalText(m.expression))) seen.add(literalText(m.expression));
        if (ts.isBinaryExpression(m) && EQ.has(m.operatorToken.kind)) {
          for (const side of [m.left, m.right]) if (OPS.includes(literalText(side))) seen.add(literalText(side));
        }
      });
      if (seen.size >= 2) dispatchers.add(n);
    });
  }
  // ---- dispatch path + op/handler taint (S3, S4) ----------------------------------------------
  if (!entryDecl) {
    set("S3", false, `${ENTRY} is not exported from ${INDEX} as a function`);
    set("S4", false, `${ENTRY} not found`);
  }
  const dispatchRoots = entryDecl ? region([entryDecl], { stopAtRegistry: true }) : new Set();
  const dispatchNodes = nodesOf(dispatchRoots);
  const taint = new Map();       // symbol -> Set(tags)
  const returns = new Map();     // function node -> Set(tags)
  const add = (map, key, tags) => {
    if (!key || !tags || tags.size === 0) return false;
    let cur = map.get(key);
    if (!cur) { cur = new Set(); map.set(key, cur); }
    let changed = false;
    for (const t of tags) if (!cur.has(t)) { cur.add(t); changed = true; }
    return changed;
  };
  const T = (...tags) => new Set(tags);
  const union = (a, b) => new Set([...a, ...b]);
  const calleeFunctions = (call) => {
    const c = unwrap(call.expression);
    if (!c || !(ts.isIdentifier(c) || ts.isPropertyAccessExpression(c))) return [];
    return targetsOfSymbol(symAt(c)).map(unwrap).filter((t) => t && isFunctionLike(t));
  };
  let lookupSites = [];
  function evalT(expr) {
    const e = unwrap(expr);
    if (!e) return T();
    if (ts.isIdentifier(e)) {
      if (isRegistry(e)) return T("REG");
      return new Set(taint.get(symAt(e)) || []);
    }
    if (ts.isPropertyAccessExpression(e)) {
      const base = evalT(e.expression);
      if (base.has("REQ") && e.name.text === "op") return T("OP");
      return T();
    }
    if (ts.isElementAccessExpression(e)) {
      const base = evalT(e.expression), key = evalT(e.argumentExpression);
      if (base.has("REQ") && literalText(e.argumentExpression) === "op") return T("OP");
      if (base.has("REG") && key.has("OP")) { lookupSites.push(e); return T("HANDLER"); }
      return T();
    }
    if (ts.isCallExpression(e)) {
      const c = unwrap(e.expression);
      if (ts.isPropertyAccessExpression(c)) {
        const recv = evalT(c.expression);
        if (recv.has("REG") && c.name.text === "get" && e.arguments.length && evalT(e.arguments[0]).has("OP")) {
          lookupSites.push(e); return T("HANDLER");
        }
        if (recv.has("REG") && ["keys", "entries", "values"].includes(c.name.text)) return T("REGKEYS");
        if (ts.isIdentifier(c.expression) && c.expression.text === "Object" && ["keys", "entries", "values", "getOwnPropertyNames"].includes(c.name.text)
          && e.arguments.length && evalT(e.arguments[0]).has("REG")) return T("REGKEYS");
      }
      let out = T();
      for (const f of calleeFunctions(e)) out = union(out, returns.get(f) || T());
      return out;
    }
    if (ts.isConditionalExpression(e)) return union(evalT(e.whenTrue), evalT(e.whenFalse));
    if (ts.isBinaryExpression(e)) {
      const k = e.operatorToken.kind;
      if (k === ts.SyntaxKind.QuestionQuestionToken || k === ts.SyntaxKind.BarBarToken) return union(evalT(e.left), evalT(e.right));
      if (k === ts.SyntaxKind.AmpersandAmpersandToken) return evalT(e.right);
      if (k === ts.SyntaxKind.EqualsToken) return evalT(e.right);
      return T();
    }
    if (ts.isAwaitExpression(e)) return evalT(e.expression);
    return T();
  }
  if (entryDecl && entryDecl.parameters.length) {
    const first = entryDecl.parameters[0].name;
    if (ts.isIdentifier(first)) add(taint, checker.getSymbolAtLocation(first), T("REQ"));
    else if (ts.isObjectBindingPattern(first)) {
      for (const el of first.elements) {
        const key = el.propertyName ? keyText(el.propertyName) : ts.isIdentifier(el.name) ? el.name.text : undefined;
        if (key === "op" && ts.isIdentifier(el.name)) add(taint, checker.getSymbolAtLocation(el.name), T("OP"));
      }
    }
  }
  for (let iter = 0; iter < 50; iter++) {
    let changed = false;
    lookupSites = [];
    for (const n of dispatchNodes) {
      if (ts.isVariableDeclaration(n) && n.initializer) {
        const t = evalT(n.initializer);
        if (ts.isIdentifier(n.name)) changed = add(taint, checker.getSymbolAtLocation(n.name), t) || changed;
        else if (ts.isObjectBindingPattern(n.name) && t.has("REQ")) {
          for (const el of n.name.elements) {
            const key = el.propertyName ? keyText(el.propertyName) : ts.isIdentifier(el.name) ? el.name.text : undefined;
            if (key === "op" && ts.isIdentifier(el.name)) changed = add(taint, checker.getSymbolAtLocation(el.name), T("OP")) || changed;
          }
        }
      } else if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.EqualsToken && ts.isIdentifier(unwrap(n.left))) {
        changed = add(taint, symAt(unwrap(n.left)), evalT(n.right)) || changed;
      } else if (ts.isCallExpression(n)) {
        for (const f of calleeFunctions(n)) {
          f.parameters.forEach((p, i) => {
            if (i < n.arguments.length && ts.isIdentifier(p.name)) {
              changed = add(taint, checker.getSymbolAtLocation(p.name), evalT(n.arguments[i])) || changed;
            } else if (i < n.arguments.length && ts.isObjectBindingPattern(p.name) && evalT(n.arguments[i]).has("REQ")) {
              for (const el of p.name.elements) {
                const key = el.propertyName ? keyText(el.propertyName) : ts.isIdentifier(el.name) ? el.name.text : undefined;
                if (key === "op" && ts.isIdentifier(el.name)) changed = add(taint, checker.getSymbolAtLocation(el.name), T("OP")) || changed;
              }
            }
          });
        }
      } else if (ts.isReturnStatement(n) && n.expression) {
        let fn = n.parent;
        while (fn && !isFunctionLike(fn)) fn = fn.parent;
        if (fn) changed = add(returns, fn, evalT(n.expression)) || changed;
      } else if (ts.isArrowFunction(n) && !ts.isBlock(n.body)) {
        changed = add(returns, n, evalT(n.body)) || changed;
      }
    }
    if (!changed) break;
  }
  // final evaluation pass: lookups, invocations, violations
  lookupSites = [];
  const invocations = [];
  const violations = [];
  const isOp = (e) => evalT(e).has("OP");
  const regLike = (e) => { const t = evalT(e); return t.has("REG") || t.has("REGKEYS"); };
  for (const n of dispatchNodes) {
    if (ts.isCallExpression(n)) {
      const c = unwrap(n.expression);
      evalT(n);
      if (evalT(c).has("HANDLER")) invocations.push(n);
      else if (ts.isPropertyAccessExpression(c) && evalT(c.expression).has("HANDLER")) invocations.push(n);
      if (ts.isPropertyAccessExpression(c) && MEMBERSHIP.has(c.name.text) && n.arguments.some(isOp) && !regLike(c.expression)) {
        violations.push(`op-derived value tested with .${c.name.text}() on something other than ${REGISTRY} @${where(n)}`);
      }
      if (ts.isPropertyAccessExpression(c) && ["hasOwn", "hasOwnProperty", "call"].includes(c.name.text)) {
        const args = n.arguments;
        const target = c.name.text === "hasOwnProperty" ? c.expression : args[0];
        const keyArgs = c.name.text === "hasOwnProperty" ? args : args.slice(1);
        if (keyArgs.some(isOp) && target && !regLike(target)) {
          violations.push(`op-derived value tested for membership in something other than ${REGISTRY} @${where(n)}`);
        }
      }
    } else if (ts.isElementAccessExpression(n)) {
      evalT(n);
      if (isOp(n.argumentExpression) && !regLike(n.expression)) {
        violations.push(`op-derived value used as a key into something other than ${REGISTRY} @${where(n)}`);
      }
    } else if (ts.isSwitchStatement(n) && isOp(n.expression)) {
      violations.push(`switch over an op-derived value @${where(n)}`);
    } else if (ts.isBinaryExpression(n)) {
      const k = n.operatorToken.kind;
      if (EQ.has(k) && (isOp(n.left) || isOp(n.right))) violations.push(`comparison of an op-derived value @${where(n)}`);
      if (k === ts.SyntaxKind.InKeyword && isOp(n.left) && !regLike(n.right)) {
        violations.push(`op-derived value tested with 'in' on something other than ${REGISTRY} @${where(n)}`);
      }
    } else if ((ts.isIfStatement(n) || ts.isConditionalExpression(n) || ts.isWhileStatement(n) || ts.isDoStatement(n))) {
      const cond = unwrap(ts.isConditionalExpression(n) ? n.condition : n.expression);
      const inner = cond && ts.isPrefixUnaryExpression(cond) ? cond.operand : cond;
      if (inner && isOp(inner)) violations.push(`condition on an op-derived value @${where(n)}`);
    }
  }
  for (const r of dispatchRoots) {
    if (dispatchers.has(r)) violations.push(`the dispatch path reaches a dispatcher @${where(r)}`);
  }
  if (entryDecl) {
    const okS3 = registryDecl && lookupSites.length > 0 && invocations.length > 0;
    set("S3", okS3, !registryDecl ? "no registry"
      : !lookupSites.length ? `the dispatch path never looks up ${REGISTRY} with an op-derived key`
        : !invocations.length ? `the handler looked up from ${REGISTRY} is never invoked on the dispatch path`
          : `lookup @${where(lookupSites[0])}; invocation @${where(invocations[0])}`);
    set("S4", violations.length === 0, violations.length ? [...new Set(violations)].slice(0, 6).join("; ")
      : `no identifier-based branching on the dispatch path (${dispatchRoots.size} region roots)`);
  }

  // ---- handler regions (S5, S6) ----------------------------------------------------------------
  const resolvedEntries = entries.map((e) => ({ ...e, roots: resolveHandler(e.handler) })).filter((e) => e.roots);
  const s5Problems = [];
  const s6Problems = [];
  const accessesLedger = (nodes) => nodes.some((n) => ts.isPropertyAccessExpression(n) && LEDGER_STATE.has(n.name.text));
  for (const op of OPS) {
    const mine = resolvedEntries.filter((e) => e.op === op);
    if (!mine.length) { s5Problems.push(`${op}: no handler`); s6Problems.push(`${op}: no handler`); continue; }
    for (const e of mine) {
      const reg = region(e.roots);
      const nodes = nodesOf(reg);
      if (entryDecl && reg.has(entryDecl)) s5Problems.push(`${op} handler reaches ${ENTRY}`);
      const disp = [...reg].filter((r) => dispatchers.has(r));
      for (const d of disp) s5Problems.push(`${op} handler reaches a dispatcher @${where(d)}`);
      if (!accessesLedger(nodes)) s6Problems.push(`${op} handler never reaches ledger state`);
    }
  }
  set("S5", registryDecl && s5Problems.length === 0, s5Problems.length ? [...new Set(s5Problems)].join("; ")
    : "no handler reaches the entry point or a dispatcher");
  if (entryDecl) {
    if (accessesLedger(dispatchNodes)) s6Problems.push("the dispatch path accesses ledger state");
    for (const n of dispatchNodes) {
      if (ts.isNewExpression(n)) {
        const s = symAt(unwrap(n.expression));
        if (s && BEHAVIOR_ERRORS.has(s.name)) s6Problems.push(`the dispatch path constructs ${s.name} @${where(n)}`);
      }
    }
  } else {
    s6Problems.push(`${ENTRY} not found`);
  }
  set("S6", registryDecl && s6Problems.length === 0, s6Problems.length ? [...new Set(s6Problems)].slice(0, 8).join("; ")
    : "every handler reaches ledger state; the dispatch path does not");
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
  const ordered = {};
  for (const r of RULES) ordered[r] = rules[r] || { ok: false, detail: "not evaluated" };
  const ok = RULES.every((r) => ordered[r].ok);
  process.stdout.write(JSON.stringify({ ok, rules: ordered }, null, 1) + "\n");
  return ok ? 0 : 1;
}

process.exitCode = main();
