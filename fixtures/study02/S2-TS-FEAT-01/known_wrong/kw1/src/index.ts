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

// INCORRECT: string-based removal on the raw query string instead of the parsed multimap. Using
// startsWith() means stripping "a" also removes "ab=2", a different parameter whose name merely
// starts with the same prefix.
export function stripParams(url: string, names: string[]): string {
  const [base, query] = splitUrl(url);
  if (!query) return url;
  const kept = query.split("&").filter((pair) => !names.some((name) => pair.startsWith(name)));
  return kept.length ? `${base}?${kept.join("&")}` : base;
}
