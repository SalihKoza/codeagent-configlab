import { Job } from "./ordering";

const retryCounts = new Map<string, number>();
const failedInfo = new Map<string, { job: Job; priority: number }>();

export function recordFailure(jobId: string, job: Job, priority: number): void {
  failedInfo.set(jobId, { job, priority });
}

export interface FailedEntry {
  jobId: string;
  job: Job;
  priority: number;
  retryCount: number;
}

export function failedEntries(): FailedEntry[] {
  return Array.from(failedInfo.entries()).map(([jobId, info]) => ({
    jobId,
    job: info.job,
    priority: info.priority,
    retryCount: retryCounts.get(jobId) ?? 0,
  }));
}

export function requeue(jobId: string): void {
  failedInfo.delete(jobId);
  retryCounts.set(jobId, (retryCounts.get(jobId) ?? 0) + 1);
}
