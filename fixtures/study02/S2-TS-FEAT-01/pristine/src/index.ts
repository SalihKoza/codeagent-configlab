import { parseParams } from "./parse";
import { encodeComponent } from "./encode";

export { parseParams };

function splitUrl(url: string): [string, string] {
  const idx = url.indexOf("?");
  if (idx === -1) return [url, ""];
  return [url.slice(0, idx), url.slice(idx + 1)];
}

function joinPairs(pairs: [string, string][]): string {
  return pairs.map(([k, v]) => `${encodeComponent(k)}=${encodeComponent(v)}`).join("&");
}

export function serialize(params: Record<string, string[]>): string {
  const pairs: [string, string][] = [];
  for (const key of Object.keys(params)) {
    for (const value of params[key]) pairs.push([key, value]);
  }
  return joinPairs(pairs);
}

function canonicalPairs(params: Record<string, string[]>): [string, string][] {
  const keys = Object.keys(params).sort();
  const pairs: [string, string][] = [];
  for (const key of keys) {
    for (const value of params[key]) pairs.push([key, value]);
  }
  return pairs;
}

export function normalize(url: string): string {
  const [base, query] = splitUrl(url);
  const params = parseParams(query);
  const pairs = canonicalPairs(params);
  return pairs.length ? `${base}?${joinPairs(pairs)}` : base;
}
