import { DuplicateCommandError, NameConflictError, UnknownCommandError } from "./errors";

/** Runs a command with its arguments and returns its output. */
export type CommandHandler = (args: readonly string[]) => string;

/** A registered command. Records are frozen; `name` is the name it was registered under. */
export interface Command {
  readonly name: string;
  readonly handler: CommandHandler;
}

interface Entry {
  readonly command: Command;
  readonly canonical: boolean;
}

/** Maps command names to handlers. */
export class CommandRegistry {
  // One table for the shared namespace: canonical names and aliases.
  private readonly names = new Map<string, Entry>();

  /**
   * Registers `handler` under `name` and returns the new (frozen) command record.
   * Throws `DuplicateCommandError` if a command named `name` is already registered, or
   * `NameConflictError` if `name` is an alias; the registry is then left unchanged.
   */
  register(name: string, handler: CommandHandler): Command {
    const existing = this.names.get(name);
    if (existing !== undefined) {
      throw existing.canonical ? new DuplicateCommandError(name) : new NameConflictError(name, "alias");
    }
    const command: Command = Object.freeze({ name, handler });
    this.names.set(name, { command, canonical: true });
    return command;
  }

  /**
   * Makes `alias` another name for the registered command `commandName`.
   * Throws `UnknownCommandError` if `commandName` is not a registered command name, otherwise
   * `NameConflictError` if `alias` is already a command name or an alias.
   */
  addAlias(alias: string, commandName: string): void {
    const target = this.names.get(commandName);
    if (target === undefined || !target.canonical) {
      throw new UnknownCommandError(commandName);
    }
    const taken = this.names.get(alias);
    if (taken !== undefined) {
      throw new NameConflictError(alias, taken.canonical ? "command" : "alias");
    }
    this.names.set(alias, { command: target.command, canonical: false });
  }

  /** The command registered under or aliased by `name` (always the same record), or `undefined`. */
  get(name: string): Command | undefined {
    return this.names.get(name)?.command;
  }

  /** Whether `get(name)` would return a command. */
  has(name: string): boolean {
    return this.names.has(name);
  }

  /**
   * Runs the command found by `get(name)` with `args` and returns the handler's result.
   * Throws `UnknownCommandError` if there is none.
   */
  run(name: string, args: readonly string[] = []): string {
    const entry = this.names.get(name);
    if (entry === undefined) {
      throw new UnknownCommandError(name);
    }
    return entry.command.handler(args);
  }

  /** All registered commands in registration order, as a new array. Aliases are not listed. */
  list(): Command[] {
    return [...this.names.values()].filter((e) => e.canonical).map((e) => e.command);
  }
}
