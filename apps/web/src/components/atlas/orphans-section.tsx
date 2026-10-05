'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { orphansNear } from '@/atlas/api';
import { type AtlasFeature, coarsePoint } from '@/atlas/types';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { failureMessage } from '@/lib/api/failure-message';
import { messages } from '@/messages';
import { entryPath } from './paths';

const O = messages.atlas.sponsor.orphans;
const A = messages.atlas;

type Load =
  | { kind: 'loading' }
  | { kind: 'ready'; next: string | null; more: boolean }
  | { kind: 'failed'; message: string };

/**
 * Orphaned entries waiting for a sponsor (decision 60): the orphaned entries around a point, each at
 * its widened place with that place's precision label and no author. The point is the
 * map's centre or the camera discovery's centre, snapped to the atlas grid before it is
 * sent; this section never asks the device for its position. It draws nothing while
 * there is nothing to offer, and nothing at all without a point.
 */
export function OrphansSection({ point }: { point: readonly [number, number] | null }) {
  const [features, setFeatures] = useState<AtlasFeature[]>([]);
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const latest = useRef(0);
  // The grid cell is the dependency: a pan inside one cell asks nothing again.
  const cell = point === null ? null : coarsePoint(point);
  const lng = cell?.[0] ?? null;
  const lat = cell?.[1] ?? null;

  const ask = async (cursor: string | null) => {
    /* v8 ignore next: narrows the type; nothing is asked without a point */
    if (lng === null || lat === null) {
      return;
    }
    const mine = ++latest.current;
    const result = await orphansNear([lng, lat], cursor);
    if (mine !== latest.current) {
      return;
    }
    if (result.ok) {
      setFeatures((current) =>
        cursor === null ? result.data.features : [...current, ...result.data.features]
      );
      setLoad({ kind: 'ready', next: result.data.next_cursor, more: false });
    } else {
      setLoad({ kind: 'failed', message: failureMessage(result) });
    }
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: `ask` closes over lng and lat; `attempt` counts the retries.
  useEffect(() => {
    if (lng === null || lat === null) {
      return;
    }
    setLoad({ kind: 'loading' });
    void ask(null);
    return () => {
      latest.current += 1;
    };
  }, [lng, lat, attempt]);

  if (point === null || (load.kind !== 'failed' && features.length === 0)) {
    return null;
  }

  return (
    <section aria-label={O.heading} className="flex flex-col gap-3">
      <h2 className="m-0 font-semibold text-[1.125rem] text-fg">{O.heading}</h2>
      <p className="m-0 text-[0.875rem] text-fg-soft leading-[1.85]">{O.lead}</p>
      <p className="m-0 text-[0.8125rem] text-fg-muted">{O.privacy}</p>
      {load.kind === 'failed' ? (
        <div role="alert" className="flex flex-col items-start gap-3">
          <Notice tone="error">{O.failed}</Notice>
          <Button variant="ghost" onClick={() => setAttempt((n) => n + 1)}>
            {A.retry}
          </Button>
        </div>
      ) : null}
      <ul aria-label={O.list} className="m-0 flex list-none flex-col gap-1 p-0">
        {features.map((feature) => (
          <li key={feature.id}>
            <Link
              href={entryPath(feature.id)}
              className="flex min-h-12 w-full flex-col items-start gap-0.5 rounded-[var(--radius-card)] px-3 py-2 text-start transition-colors duration-200 hover:bg-surface"
            >
              <span className="font-semibold text-fg">{feature.properties.title}</span>
              <span className="text-[0.8125rem] text-fg-muted">
                {A.joinLabels([
                  feature.properties.place?.label,
                  feature.properties.place?.country_label,
                ])}
              </span>
              <span className="text-[0.8125rem] text-fg-muted">
                {feature.properties.precision_label}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {load.kind === 'ready' && load.next !== null ? (
        <Button
          variant="ghost"
          className="self-start"
          disabled={load.more}
          onClick={() => {
            setLoad({ ...load, more: true });
            void ask(load.next);
          }}
        >
          {load.more ? O.loadingMore : O.more}
        </Button>
      ) : null}
    </section>
  );
}
