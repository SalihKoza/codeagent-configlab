export interface Job {
  id: string;
  payload?: unknown;
}

interface HeapEntry {
  job: Job;
  priority: number;
}

// INCORRECT: a binary-heap-backed reimplementation. Heaps do not guarantee FIFO order among
// equal-priority elements — sibling swaps during sift-down can reorder them relative to their
// original insertion order, silently breaking the existing tie-break contract.
export class PriorityIndex {
  private heap: HeapEntry[] = [];

  insert(job: Job, priority: number): void {
    this.heap.push({ job, priority });
    let i = this.heap.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (this.heap[parent].priority >= this.heap[i].priority) break;
      [this.heap[parent], this.heap[i]] = [this.heap[i], this.heap[parent]];
      i = parent;
    }
  }

  popHighest(): { job: Job; priority: number } | undefined {
    if (this.heap.length === 0) return undefined;
    const top = this.heap[0];
    const last = this.heap.pop() as HeapEntry;
    if (this.heap.length > 0) {
      this.heap[0] = last;
      let i = 0;
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const l = 2 * i + 1;
        const r = 2 * i + 2;
        let largest = i;
        if (l < this.heap.length && this.heap[l].priority > this.heap[largest].priority) largest = l;
        if (r < this.heap.length && this.heap[r].priority > this.heap[largest].priority) largest = r;
        if (largest === i) break;
        [this.heap[i], this.heap[largest]] = [this.heap[largest], this.heap[i]];
        i = largest;
      }
    }
    return top;
  }

  size(): number {
    return this.heap.length;
  }
}
