import { cardKey, createPngCache } from './cache';
import type { PublicInsight } from './layout';
import { createLimiter } from './limiter';
import { renderCard } from './render';

/** Two cards at a time per process, four more waiting; a card is about 100 ms of work. */
const CONCURRENT = 2;
const QUEUED = 4;
/** Cards kept: at most a few megabytes. */
const KEPT = 32;

const limiter = createLimiter(CONCURRENT, QUEUED);
const cache = createPngCache(KEPT);

/** The card of an insight: from memory when this very content was just drawn, else drawn within the limits. */
export async function cardPng(insight: PublicInsight, host: string): Promise<Buffer> {
  const key = cardKey(insight, host);
  const known = cache.get(key);
  if (known !== undefined) {
    return known;
  }
  const png = await limiter.run(() => renderCard(insight, host));
  cache.set(key, png);
  return png;
}
