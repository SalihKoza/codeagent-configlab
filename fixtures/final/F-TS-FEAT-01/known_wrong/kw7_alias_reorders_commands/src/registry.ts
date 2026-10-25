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
  private readonly commands = new Map<string, Command>();
  private readonly aliases = new Map<string, string>();

  /**
   * Registers `handler` under `name` and returns the new (frozen) command record.
   * Throws `DuplicateCommandError` if a command named `name` is already registered, or
   * `NameConflictError` if `name` is an alias; the registry is then left unchanged.
   */
  register(name: string, handler: CommandHandler): Command {
    if (this.commands.has(name)) {
      throw new DuplicateCommandError(name);
    }
    if (this.aliases.has(name)) {
      throw new NameConflictError(name, "alias");
    }
    const command: Command = Object.freeze({ name, handler });
    this.commands.set(name, command);
    return command;
  }

  /**
   * Makes `alias` another name for the registered command `commandName`.
   * Throws `UnknownCommandError` if `commandName` is not a registered command name, otherwise
   * `NameConflictError` if `alias` is already a command name or an alias.
   */
  addAlias(alias: string, commandName: string): void {
    if (!this.commands.has(commandName)) {
      throw new UnknownCommandError(commandName);
    }
    if (this.commands.has(alias)) {
      throw new NameConflictError(alias, "command");
    }
    if (this.aliases.has(alias)) {
      throw new NameConflictError(alias, "alias");
    }
    this.aliases.set(alias, commandName);
    // Re-store the command so its entry is refreshed together with the new alias.
    const command = this.commands.get(commandName)!;
    this.commands.delete(commandName);
    this.commands.set(commandName, command);
  }

  /** The command registered under or aliased by `name` (always the same record), or `undefined`. */
  get(name: string): Command | undefined {
    const target = this.aliases.get(name);
    return this.commands.get(target === undefined ? name : target);
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
    return [...this.commands.values()];
  }
}
