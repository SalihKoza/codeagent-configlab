export interface Job {
  id: string;
  payload?: unknown;
}

interface Entry {
  job: Job;
  priority: number;
  seq: number;
}

let pending: Entry[] = [];
let seqCounter = 0;

export function insert(job: Job, priority: number): void {
  pending.push({ job, priority, seq: seqCounter++ });
  pending.sort((a, b) => {
    if (a.priority !== b.priority) return b.priority - a.priority;
    return a.seq - b.seq;
  });
}

export function popHighest(): { job: Job; priority: number } | undefined {
  const entry = pending.shift();
  return entry ? { job: entry.job, priority: entry.priority } : undefined;
}

export function pendingSize(): number {
  return pending.length;
}
