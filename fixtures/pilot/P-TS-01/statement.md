# contact-export — consolidate field normalization

This package exports contact records to three formats: `toCsv`, `toJson` and `toMarkdown`
(`src/csv.ts`, `src/json.ts`, `src/markdown.ts`, re-exported from `src/index.ts`). Each of the
three exporters currently normalizes each field (`name`, `email`, `notes`) with its own private
helper function before formatting it. The three helpers are functionally identical:

- `null` or `undefined` becomes the empty string `""`.
- Any other value is first converted to a string (as if by `String(value)`).
- The resulting string is then trimmed of leading and trailing whitespace, and every internal run
  of one or more whitespace characters (space, tab `\t`, newline `\n`, carriage return `\r`) is
  collapsed to a single space character.

## Required change

Consolidate this duplicated logic into one shared function:

- Create `src/normalize.ts`, exporting a function `normalizeField(value: unknown): string` that
  implements the normalization rule above.
- `src/csv.ts`, `src/json.ts` and `src/markdown.ts` must import `normalizeField` from
  `./normalize` and use it wherever they currently normalize a field. Their own private
  per-file normalization helpers must no longer exist.
- Formatting that is specific to one exporter (CSV quoting of values containing a comma, quote
  or newline; Markdown escaping of the `|` character) is not normalization and must stay local to
  its own exporter file — it must not move into `normalizeField`.
- `toCsv`, `toJson` and `toMarkdown` must retain their existing signatures. The new export
  `normalizeField` must have exactly the signature `normalizeField(value: unknown): string`. For
  every input, `toCsv`, `toJson` and `toMarkdown` must return exactly the same output as before
  this change.

This is a pure refactor: no new behavior is requested and no existing behavior may change.

## Running the build and tests

    npm run build
    npm test

(`npm run build` compiles `src/` and `test/` with the pinned `typescript` compiler into `dist/`;
`npm test` runs the compiled tests with Node's built-in test runner. Both work offline —
`typescript` is already installed in `node_modules/`.)
