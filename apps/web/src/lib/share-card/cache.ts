import { createHash } from 'node:crypto';

/*
 * A small, in-process memory of the cards just drawn, so a card shared widely
 * is drawn once, not at every request. The key is made of the content: the
 * API's answer for the insight and the host written on the card. The API is
 * still asked at every request, so a withdrawn insight answers 404 at once and
 * nothing here can show it again; an edited insight has another key. Nothing
 * is written to disk and a restart forgets everything.
 */

export interface PngCache {
  get(key: string): Buffer | undefined;
  set(key: string, png: Buffer): void;
}

export function cardKey(insight: unknown, host: string): string {
  return createHash('sha256')
    .update(JSON.stringify(insight))
    .update('\n')
    .update(host)
    .digest('hex');
}

/** Least recently used out first. */
export function createPngCache(capacity: number): PngCache {
  const entries = new Map<string, Buffer>();
  return {
    get(key) {
      const png = entries.get(key);
      if (png !== undefined) {
        entries.delete(key);
        entries.set(key, png);
      }
      return png;
    },
    set(key, png) {
      entries.delete(key);
      entries.set(key, png);
      if (entries.size > capacity) {
        entries.delete(entries.keys().next().value as string);
      }
    },
  };
}
