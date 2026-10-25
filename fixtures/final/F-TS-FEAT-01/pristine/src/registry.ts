import { DuplicateCommandError, UnknownCommandError } from "./errors";

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

  /**
   * Registers `handler` under `name` and returns the new (frozen) command record.
   * Throws `DuplicateCommandError` if a command named `name` is already registered; the registry
   * is then left unchanged.
   */
  register(name: string, handler: CommandHandler): Command {
    if (this.commands.has(name)) {
      throw new DuplicateCommandError(name);
    }
    const command: Command = Object.freeze({ name, handler });
    this.commands.set(name, command);
    return command;
  }

  /** The command registered under `name` (always the same record object), or `undefined`. */
  get(name: string): Command | undefined {
    return this.commands.get(name);
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

  /** All registered commands in registration order, as a new array. */
  list(): Command[] {
    return [...this.commands.values()];
  }
}
