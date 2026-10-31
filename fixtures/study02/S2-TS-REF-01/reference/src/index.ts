import { PriorityIndex, Job } from "./ordering";
import { recordFailure } from "./retries";

export type { Job };

interface InFlightEntry {
  job: Job;
  priority: number;
}

const priorityIndex = new PriorityIndex();
const inFlight = new Map<string, InFlightEntry>();

export function enqueue(job: Job, priority: number): void {
  priorityIndex.insert(job, priority);
}

export function next(): Job | undefined {
  const entry = priorityIndex.popHighest();
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
  return priorityIndex.size();
}
