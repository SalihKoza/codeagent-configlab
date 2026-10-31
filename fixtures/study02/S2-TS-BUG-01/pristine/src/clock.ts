// Injectable time source. All time-dependent code must read "now" through this module rather
// than calling Date.now() directly, so tests can control time deterministically.
export let now: () => number = () => Date.now();

export function setClock(fn: () => number): void {
  now = fn;
}
