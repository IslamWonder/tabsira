'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { failureMessage } from '@/lib/api/failure-message';
import type { Failure, Result } from '@/lib/api/result';

/*
 * A list the API hands out a page at a time behind an opaque cursor. The first
 * page loads on display; the next one on request (a button, never a scroll
 * listener: docs/SEO.md). A late answer for a list that was replaced is
 * dropped, so a reply for the previous tab never writes over the current one
 * (tajriba §8).
 */

export interface Page<T, R = string> {
  items: T[];
  next_cursor: string | null;
  empty_reason?: R | null;
}

export type PagesStatus =
  | { kind: 'loading' }
  | { kind: 'ready'; emptyReason: string | null; more: boolean }
  | { kind: 'loading-more' }
  | { kind: 'failed'; message: string; failure: Failure };

export interface Pages<T> {
  items: T[];
  status: PagesStatus;
  loadMore: () => void;
  reload: () => void;
  /**
   * Replaces one item in place (after a like, a save, a submit); `null` removes
   * it. An updater function receives the item the list holds right now, so an
   * answer that lands after another change never writes over it with what an
   * earlier render saw.
   */
  replace: (match: (item: T) => boolean, next: T | null | ((item: T) => T | null)) => void;
  /** Puts an item at the top (a new comment, a new post). */
  prepend: (item: T) => void;
  append: (item: T) => void;
}

/**
 * `fetchPage` is called with the cursor of the previous page, null for the
 * first. `key` names the list: when it changes, the list starts over.
 */
export function usePages<T>(
  fetchPage: (cursor: string | null) => Promise<Result<Page<T, string>>>,
  key: string,
  /** False while something the list depends on (the session) is not known yet: nothing is asked. */
  enabled = true
): Pages<T> {
  const [items, setItems] = useState<T[]>([]);
  const [status, setStatus] = useState<PagesStatus>({ kind: 'loading' });
  const cursor = useRef<string | null>(null);
  const generation = useRef(0);
  // The generation a load is running for: a second «load more» for the same
  // list waits instead of appending the same page twice.
  const loading = useRef<number | null>(null);

  const load = useCallback(
    async (first: boolean) => {
      if (!first && loading.current === generation.current) {
        return;
      }
      const mine = first ? ++generation.current : generation.current;
      loading.current = mine;
      try {
        setStatus(first ? { kind: 'loading' } : { kind: 'loading-more' });
        const result = await fetchPage(first ? null : cursor.current);
        if (mine !== generation.current) {
          return;
        }
        if (!result.ok) {
          setStatus({ kind: 'failed', message: failureMessage(result), failure: result });
          return;
        }
        cursor.current = result.data.next_cursor;
        setItems((current) => (first ? result.data.items : [...current, ...result.data.items]));
        setStatus({
          kind: 'ready',
          emptyReason: first ? (result.data.empty_reason ?? null) : null,
          more: result.data.next_cursor !== null,
        });
      } finally {
        if (loading.current === mine) {
          loading.current = null;
        }
      }
    },
    [fetchPage]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: `key` names the list; a new key starts over.
  useEffect(() => {
    setItems([]);
    cursor.current = null;
    if (enabled) {
      void load(true);
    } else {
      generation.current += 1;
      setStatus({ kind: 'loading' });
    }
  }, [key, load, enabled]);

  const replace = useCallback(
    (match: (item: T) => boolean, next: T | null | ((item: T) => T | null)) => {
      setItems((current) =>
        current.flatMap((item) => {
          if (!match(item)) {
            return [item];
          }
          // A function here is always the updater; T itself is a data record.
          const updated = typeof next === 'function' ? (next as (item: T) => T | null)(item) : next;
          return updated === null ? [] : [updated];
        })
      );
    },
    []
  );

  return {
    items,
    status,
    loadMore: () => void load(false),
    reload: () => void load(true),
    replace,
    prepend: useCallback((item: T) => setItems((current) => [item, ...current]), []),
    append: useCallback((item: T) => setItems((current) => [...current, item]), []),
  };
}
