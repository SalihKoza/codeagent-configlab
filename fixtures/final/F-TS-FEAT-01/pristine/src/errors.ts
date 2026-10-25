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
