import type { ContactRecord } from "./types";
import { normalizeField } from "./normalize";

function cleanMdValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  const s = typeof value === "string" ? value : String(value);
  return s.trim().replace(/\s+/g, " ");
}

function mdEscape(value: string): string {
  return value.replace(/\|/g, "\\|");
}

export function toMarkdown(records: ContactRecord[]): string {
  const header = "| name | email | notes |";
  const sep = "| --- | --- | --- |";
  const rows = records.map(r => {
    normalizeField(r.name); // called, but discarded
    return `| ${mdEscape(cleanMdValue(r.name))} | ${mdEscape(cleanMdValue(r.email))} | ` +
           `${mdEscape(cleanMdValue(r.notes))} |`;
  });
  return [header, sep, ...rows].join("\n");
}
