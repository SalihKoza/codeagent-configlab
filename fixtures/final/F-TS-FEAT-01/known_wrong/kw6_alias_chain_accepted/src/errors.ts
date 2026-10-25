/** Thrown by `register` when a command with the same name is already registered. */
export class DuplicateCommandError extends Error {
  readonly commandName: string;

  constructor(commandName: string) {
    super(`Command already registered: ${commandName}`);
    this.name = "DuplicateCommandError";
    this.commandName = commandName;
  }
}

/** Thrown when a name does not identify a registered command. */
export class UnknownCommandError extends Error {
  readonly commandName: string;

  constructor(commandName: string) {
    super(`Unknown command: ${commandName}`);
    this.name = "UnknownCommandError";
    this.commandName = commandName;
  }
}

/**
 * Thrown when a name is already taken in the shared command/alias namespace.
 * `existing` says what currently holds `conflictName`.
 */
export class NameConflictError extends Error {
  readonly conflictName: string;
  readonly existing: "command" | "alias";

  constructor(conflictName: string, existing: "command" | "alias") {
    super(`Name already in use by ${existing === "command" ? "a command" : "an alias"}: ${conflictName}`);
    this.name = "NameConflictError";
    this.conflictName = conflictName;
    this.existing = existing;
  }
}
