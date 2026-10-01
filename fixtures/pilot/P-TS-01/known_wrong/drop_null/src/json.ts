import type { ContactRecord } from "./types";
import { normalizeField } from "./normalize";

export function toJson(records: ContactRecord[]): string {
  const cleaned = records.map(r => ({
    name: normalizeField(r.name), email: normalizeField(r.email), notes: normalizeField(r.notes),
  }));
  return JSON.stringify(cleaned, null, 2);
}
