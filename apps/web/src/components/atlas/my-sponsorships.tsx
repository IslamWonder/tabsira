'use client';

import { useEffect, useState } from 'react';
import { mySponsorships } from '@/atlas/api';
import type { Sponsorship } from '@/atlas/types';
import { Button, LinkButton } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { failureMessage } from '@/lib/api/failure-message';
import { formatDay } from '@/lib/dates';
import { messages } from '@/messages';
import { entryPath } from './paths';

const L = messages.atlas.sponsor.list;
const A = messages.atlas;

type Load =
  | { kind: 'loading' }
  | { kind: 'ready'; items: Sponsorship[] }
  | { kind: 'failed'; message: string };

/**
 * The member's current sponsorships (one that ends is deleted, so none is listed as ended).
 * A plain list; it adds up nothing and ranks nothing.
 */
export function MySponsorships() {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` counts the retries; each one asks again.
  useEffect(() => {
    let current = true;
    setLoad({ kind: 'loading' });
    void mySponsorships().then((result) => {
      if (!current) {
        return;
      }
      setLoad(
        result.ok
          ? { kind: 'ready', items: result.data }
          : { kind: 'failed', message: failureMessage(result) }
      );
    });
    return () => {
      current = false;
    };
  }, [attempt]);

  return (
    <section aria-label={L.heading} className="flex flex-col gap-3">
      <h2 className="m-0 font-semibold text-[1.125rem] text-fg">{L.heading}</h2>
      {load.kind === 'loading' ? (
        <p role="status" className="m-0 text-fg-muted">
          {L.loading}
        </p>
      ) : null}
      {load.kind === 'failed' ? (
        <div role="alert" className="flex flex-col items-start gap-3">
          <Notice tone="error">{load.message}</Notice>
          <Button variant="ghost" onClick={() => setAttempt((n) => n + 1)}>
            {A.retry}
          </Button>
        </div>
      ) : null}
      {load.kind === 'ready' && load.items.length === 0 ? (
        <p role="status" className="m-0 text-fg-soft leading-[1.85]">
          {L.empty} {L.emptyHint}
        </p>
      ) : null}
      {load.kind === 'ready' ? (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {load.items.map((item) => (
            <li
              key={`${item.entry_id}-${item.started_at}`}
              className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-line px-3 py-2.5"
            >
              <div className="flex flex-col gap-1">
                <span className="font-semibold text-fg">{item.title}</span>
                <span className="text-[0.8125rem] text-fg-muted">
                  {A.joinLabels([item.place?.label, L.since(formatDay(item.started_at))])}
                </span>
              </div>
              <div>
                <LinkButton
                  href={entryPath(item.entry_id)}
                  variant="secondary"
                  className="min-h-10 px-3 text-[0.875rem]"
                >
                  {L.open}
                </LinkButton>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
