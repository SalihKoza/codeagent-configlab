import { decodeComponent } from "./encode";

export function parseParams(query: string): Record<string, string[]> {
  const q = query.startsWith("?") ? query.slice(1) : query;
  const result: Record<string, string[]> = {};
  if (q.length === 0) return result;
  for (const pair of q.split("&")) {
    if (pair.length === 0) continue;
    const eq = pair.indexOf("=");
    const rawKey = eq === -1 ? pair : pair.slice(0, eq);
    const rawValue = eq === -1 ? "" : pair.slice(eq + 1);
    const key = decodeComponent(rawKey);
    const value = decodeComponent(rawValue);
    if (!result[key]) result[key] = [];
    result[key].push(value);
  }
  return result;
}
