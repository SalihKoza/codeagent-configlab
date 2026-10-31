export interface Job {
  id: string;
  payload?: unknown;
}

interface Entry {
  job: Job;
  priority: number;
  seq: number;
}

export class PriorityIndex {
  private entries: Entry[] = [];
  private seqCounter = 0;

  insert(job: Job, priority: number): void {
    this.entries.push({ job, priority, seq: this.seqCounter++ });
    this.entries.sort((a, b) => {
      if (a.priority !== b.priority) return b.priority - a.priority;
      return a.seq - b.seq;
    });
  }

  popHighest(): { job: Job; priority: number } | undefined {
    const entry = this.entries.shift();
    return entry ? { job: entry.job, priority: entry.priority } : undefined;
  }

  size(): number {
    return this.entries.length;
  }
}
