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
  const pairs: [string, string][] = [];
  for (const key of Object.keys(params)) {
    for (const value of params[key]) pairs.push([key, value]);
  }
  pairs.sort((a, b) => {
    if (a[0] !== b[0]) return a[0] < b[0] ? -1 : 1;
    if (a[1] !== b[1]) return a[1] < b[1] ? -1 : 1;
    return 0;
  });
  return pairs;
}

export function normalize(url: string): string {
  const [base, query] = splitUrl(url);
  const params = parseParams(query);
  const pairs = canonicalPairs(params);
  return pairs.length ? `${base}?${joinPairs(pairs)}` : base;
}
