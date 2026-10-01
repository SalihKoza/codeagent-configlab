export function normalizeField(value: unknown): string {
  if (value === null || value === undefined) return "";
  const s = typeof value === "string" ? value : String(value);
  return s.trim().replace(/\s+/g, " ");
}
