import type { ContactRecord } from "./types";
import { normalizeField } from "./normalize";

function cleanJsonValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  const s = typeof value === "string" ? value : String(value);
  return s.trim().replace(/\s+/g, " ");
}

export function toJson(records: ContactRecord[]): string {
  const cleaned = records.map(r => {
    normalizeField(r.name); // called, but discarded
    return {
      name: cleanJsonValue(r.name), email: cleanJsonValue(r.email), notes: cleanJsonValue(r.notes),
    };
  });
  return JSON.stringify(cleaned, null, 2);
}
