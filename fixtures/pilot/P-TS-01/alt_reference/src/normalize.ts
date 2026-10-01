export function normalizeField(value: unknown): string {
  if (value === null || value === undefined) return "";
  const s = typeof value === "string" ? value : String(value);
  let result = "";
  let pendingSpace = false;
  for (const ch of s) {
    const isWs = ch === " " || ch === "\t" || ch === "\n" || ch === "\r";
    if (isWs) {
      if (result.length > 0) pendingSpace = true;
      continue;
    }
    if (pendingSpace) {
      result += " ";
      pendingSpace = false;
    }
    result += ch;
  }
  return result;
}
