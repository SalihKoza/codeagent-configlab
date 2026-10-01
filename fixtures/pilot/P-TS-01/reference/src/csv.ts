import type { ContactRecord } from "./types";
import { normalizeField } from "./normalize";

function csvEscape(value: string): string {
  if (/[",\n]/.test(value)) {
    return '"' + value.replace(/"/g, '""') + '"';
  }
  return value;
}

export function toCsv(records: ContactRecord[]): string {
  const header = "name,email,notes";
  const rows = records.map(r =>
    [csvEscape(normalizeField(r.name)), csvEscape(normalizeField(r.email)),
     csvEscape(normalizeField(r.notes))].join(","));
  return [header, ...rows].join("\n");
}
