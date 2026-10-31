import { now } from "./clock";

const store = new Map<string, number>();

function isExpired(expiry: number): boolean {
  return now() >= expiry;
}

export function markSeen(eventId: string, ttlMs: number): void {
  store.set(eventId, now() + ttlMs);
}

export function seen(eventId: string): boolean {
  const expiry = store.get(eventId);
  if (expiry === undefined) return false;
  return !isExpired(expiry);
}

export function purgeExpired(): number {
  let removed = 0;
  for (const [id, expiry] of Array.from(store.entries())) {
    if (isExpired(expiry)) {
      store.delete(id);
      removed++;
    }
  }
  return removed;
}
