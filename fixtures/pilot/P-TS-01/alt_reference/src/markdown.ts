import type { ContactRecord } from "./types";
import { normalizeField } from "./normalize";

function mdEscape(value: string): string {
  return value.replace(/\|/g, "\\|");
}

export function toMarkdown(records: ContactRecord[]): string {
  const header = "| name | email | notes |";
  const sep = "| --- | --- | --- |";
  const rows = records.map(r =>
    `| ${mdEscape(normalizeField(r.name))} | ${mdEscape(normalizeField(r.email))} | ` +
    `${mdEscape(normalizeField(r.notes))} |`);
  return [header, sep, ...rows].join("\n");
}
