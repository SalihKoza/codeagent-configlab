import { now } from "./clock";

const store = new Map<string, number>();

export function markSeen(eventId: string, ttlMs: number): void {
  store.set(eventId, now() + ttlMs);
}

// INCORRECT FIX: changes seen()'s operator instead of purgeExpired()'s, landing on the wrong
// overall convention (treats the boundary instant as still-valid instead of expired).
export function seen(eventId: string): boolean {
  const expiry = store.get(eventId);
  if (expiry === undefined) return false;
  return now() <= expiry;
}

export function purgeExpired(): number {
  let removed = 0;
  for (const [id, expiry] of Array.from(store.entries())) {
    if (now() > expiry) {
      store.delete(id);
      removed++;
    }
  }
  return removed;
}
