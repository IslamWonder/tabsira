/*
 * A card is drawn for anyone who asks, so drawing is bounded in this process:
 * a few at a time, a short queue behind them, and a refusal beyond it. nginx
 * limits the requests per address; this limits what one process takes on.
 */

export class Busy extends Error {
  constructor() {
    super('the share card renderer is busy');
  }
}

export interface Limiter {
  run<T>(task: () => Promise<T>): Promise<T>;
}

export function createLimiter(concurrent: number, queued: number): Limiter {
  let active = 0;
  const waiting: (() => void)[] = [];

  const release = () => {
    const next = waiting.shift();
    if (next === undefined) {
      active -= 1;
    } else {
      next();
    }
  };

  return {
    async run(task) {
      if (active >= concurrent) {
        if (waiting.length >= queued) {
          throw new Busy();
        }
        // The slot is handed over, not freed, so `active` stays as it is.
        await new Promise<void>((resolve) => waiting.push(resolve));
      } else {
        active += 1;
      }
      try {
        return await task();
      } finally {
        release();
      }
    },
  };
}
