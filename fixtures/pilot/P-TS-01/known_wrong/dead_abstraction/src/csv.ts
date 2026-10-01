import type { ContactRecord } from "./types";
import { normalizeField } from "./normalize";

function cleanCsvValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  const s = typeof value === "string" ? value : String(value);
  return s.trim().replace(/\s+/g, " ");
}

function csvEscape(value: string): string {
  if (/[",\n]/.test(value)) return '"' + value.replace(/"/g, '""') + '"';
  return value;
}

export function toCsv(records: ContactRecord[]): string {
  const header = "name,email,notes";
  const rows = records.map(r => {
    normalizeField(r.name); // called, but discarded -- cleanCsvValue still does the real work
    return [csvEscape(cleanCsvValue(r.name)), csvEscape(cleanCsvValue(r.email)),
            csvEscape(cleanCsvValue(r.notes))].join(",");
  });
  return [header, ...rows].join("\n");
}
