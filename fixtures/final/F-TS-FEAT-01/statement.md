# command-registry — add command aliases

`src/registry.ts` provides `CommandRegistry`, re-exported from `src/index.ts`. A registry maps
command names to handlers (`CommandHandler = (args: readonly string[]) => string`):

- `register(name, handler)` registers a command and returns its frozen record
  (`Command`: `{ name, handler }`); a name that is already registered raises
  `DuplicateCommandError`;
- `get(name)` returns the command record (always the same object) or `undefined`; `has(name)`
  tells whether `get(name)` would return a command;
- `run(name, args?)` calls the command's handler and returns its result; an unknown name raises
  `UnknownCommandError`;
- `list()` returns the registered commands in registration order, as a new array.

## Feature request

Users want to call commands by alternative names. Add aliases to `CommandRegistry`:

```ts
addAlias(alias: string, commandName: string): void
```

Example:

```ts
const registry = new CommandRegistry();
const status = registry.register("status", (args) => `status ${args.join(" ")}`);
registry.register("commit", (args) => `commit ${args.join(" ")}`);
registry.addAlias("st", "status");
registry.addAlias("ci", "commit");

registry.get("st") === status;       // true
registry.run("ci", ["-m", "x"]);     // "commit -m x"
registry.list().map((c) => c.name);  // ["status", "commit"]
registry.register("st", () => "");   // throws NameConflictError (existing: "alias")
```

## New behavior

1. `addAlias(alias, commandName)` makes `alias` an alternative name for the registered command
   whose canonical name (the name it was registered under) is `commandName`. It returns
   `undefined`.
2. After a successful `addAlias`, `get(alias)` returns the **same `Command` object** as
   `get(commandName)` (its `name` is still the canonical name), `has(alias)` is `true`, and
   `run(alias, args)` calls that command's handler with `args` and returns its result.
3. Aliases are not commands. `list()` still returns only the registered commands — the same record
   objects, in the same registration order as without aliases. Adding aliases never adds, removes,
   reorders, replaces or modifies command records.
4. A command may have any number of aliases.

## Name rules

Command names and aliases share **one namespace**: a name is either free, the canonical name of
exactly one command, or an alias of exactly one command. Names are compared exactly (case and
whitespace matter).

5. An alias must target a canonical command name directly. Aliases of aliases are not supported.
6. An alias cannot be a name that is already a command name — including the target command's own
   name.
7. An alias cannot be a name that is already an alias — whether of the same command or of another
   one. Existing aliases are never overwritten; adding the identical alias again is rejected too.
8. `register` cannot take a name that is already an alias; a later command never takes over an
   alias.
9. A rejected call changes nothing: every command, alias and the listing stay exactly as they were.

## Errors

Add and export a new error class `NameConflictError` (a subclass of `Error`) with:

- `name`: `"NameConflictError"`;
- `conflictName`: the name that is already taken;
- `existing`: `"command"` if that name is a command name, `"alias"` if it is an alias;
- `message`: `Name already in use by a command: <conflictName>` or
  `Name already in use by an alias: <conflictName>` respectively.

`addAlias(alias, commandName)` checks, in this order:

10. If `commandName` is not the canonical name of a registered command (it is unknown, **or it is
    an alias**), it raises the existing `UnknownCommandError` for `commandName`
    (`commandName` property and message `Unknown command: <commandName>` as today). This check
    comes first: for example, `addAlias("st", "nothing")` raises `UnknownCommandError` even when
    `st` is already taken.
11. Otherwise, if `alias` is a command name (rule 6), it raises
    `NameConflictError` with `existing: "command"`.
12. Otherwise, if `alias` is already an alias (rule 7), it raises `NameConflictError` with
    `existing: "alias"`.

`register(name, handler)`:

13. If `name` is already a command name, it raises `DuplicateCommandError` exactly as before.
14. If `name` is an alias, it raises `NameConflictError` with `existing: "alias"`.

(Because there is one namespace, at most one of 13 and 14 can apply.)

## Unchanged behavior

15. Registration, lookup, `has`, `run`, listing and the existing errors (`DuplicateCommandError`,
    `UnknownCommandError`: classes, `name`, `commandName`, messages) behave exactly as before for
    every name that is not an alias.
16. Existing exports, types (`Command`, `CommandHandler`) and method signatures stay unchanged; the
    only additions are `addAlias` and `NameConflictError`.

## Constraints

- Do not add dependencies.
- Do not change existing behavior beyond what is described above.

## Running the public tests

    npm run build
    npm test
