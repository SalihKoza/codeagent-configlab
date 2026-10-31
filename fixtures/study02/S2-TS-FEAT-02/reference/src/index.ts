import { insert, popHighest, pendingSize, Job } from "./ordering";
import { recordFailure, failedEntries, requeue } from "./retries";

export type { Job };

interface InFlightEntry {
  job: Job;
  priority: number;
}

const inFlight = new Map<string, InFlightEntry>();

export function enqueue(job: Job, priority: number): void {
  insert(job, priority);
}

export function next(): Job | undefined {
  const entry = popHighest();
  if (!entry) return undefined;
  inFlight.set(entry.job.id, { job: entry.job, priority: entry.priority });
  return entry.job;
}

export function markFailed(jobId: string): void {
  const info = inFlight.get(jobId);
  if (!info) return;
  inFlight.delete(jobId);
  recordFailure(jobId, info.job, info.priority);
}

export function size(): number {
  return pendingSize();
}

export function requeueFailed(maxRetries: number): void {
  for (const entry of failedEntries()) {
    if (entry.retryCount < maxRetries) {
      insert(entry.job, entry.priority);
      requeue(entry.jobId);
    }
  }
}
