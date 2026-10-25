import { DuplicateCommandError, NameConflictError, UnknownCommandError } from "./errors";

/** Runs a command with its arguments and returns its output. */
export type CommandHandler = (args: readonly string[]) => string;

/** A registered command. Records are frozen; `name` is the name it was registered under. */
export interface Command {
  readonly name: string;
  readonly handler: CommandHandler;
}

/** Maps command names to handlers. */
export class CommandRegistry {
  private readonly ordered: Command[] = [];
  private readonly byName = new Map<string, Command>();
  // Alias name -> the canonical command record itself.
  private readonly aliasRecords = new Map<string, Command>();

  private nameHolder(name: string): "command" | "alias" | null {
    if (this.byName.has(name)) {
      return "command";
    }
    return this.aliasRecords.has(name) ? "alias" : null;
  }

  /**
   * Registers `handler` under `name` and returns the new (frozen) command record.
   * Throws `DuplicateCommandError` if a command named `name` is already registered, or
   * `NameConflictError` if `name` is an alias; the registry is then left unchanged.
   */
  register(name: string, handler: CommandHandler): Command {
    switch (this.nameHolder(name)) {
      case "command":
        throw new DuplicateCommandError(name);
      case "alias":
        throw new NameConflictError(name, "alias");
    }
    const command: Command = Object.freeze({ name, handler });
    this.ordered.push(command);
    this.byName.set(name, command);
    return command;
  }

  /**
   * Makes `alias` another name for the registered command `commandName`.
   * Throws `UnknownCommandError` if `commandName` is not a registered command name, otherwise
   * `NameConflictError` if `alias` is already a command name or an alias.
   */
  addAlias(alias: string, commandName: string): void {
    const command = this.byName.get(commandName);
    if (command === undefined) {
      throw new UnknownCommandError(commandName);
    }
    const holder = this.nameHolder(alias);
    if (holder !== null) {
      throw new NameConflictError(alias, holder);
    }
    this.aliasRecords.set(alias, command);
  }

  /** The command registered under or aliased by `name` (always the same record), or `undefined`. */
  get(name: string): Command | undefined {
    return this.byName.get(name) ?? this.aliasRecords.get(name);
  }

  /** Whether `get(name)` would return a command. */
  has(name: string): boolean {
    return this.get(name) !== undefined;
  }

  /**
   * Runs the command found by `get(name)` with `args` and returns the handler's result.
   * Throws `UnknownCommandError` if there is none.
   */
  run(name: string, args: readonly string[] = []): string {
    const command = this.get(name);
    if (command === undefined) {
      throw new UnknownCommandError(name);
    }
    return command.handler(args);
  }

  /** All registered commands in registration order, as a new array. Aliases are not listed. */
  list(): Command[] {
    return this.ordered.slice();
  }
}
