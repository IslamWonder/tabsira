'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { getPlace } from '@/atlas/api';
import type { AtlasFeature, AtlasPlace } from '@/atlas/types';
import { lngLatOf } from '@/atlas/types';
import { StatusScreen } from '@/components/app/status-screen';
import { AtlasIcon } from '@/components/icons';
import { MapLayout } from '@/components/layout/layouts';
import { Button, LinkButton } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { failureMessage } from '@/lib/api/failure-message';
import type { Failure } from '@/lib/api/result';
import { messages } from '@/messages';
import { EntryCard } from './atlas-screen';
import { MapView } from './map-view';

const A = messages.atlas;

type Load =
  | { kind: 'loading' }
  | {
      kind: 'ready';
      place: AtlasPlace;
      entries: AtlasFeature[];
      cursor: string | null;
      more: boolean;
    }
  | { kind: 'missing' }
  | { kind: 'failed'; failure: Failure };

/**
 * The memory of a place: a public place and the published entries labelled with it,
 * newest first, each with what it adds. The map shows the place and its
 * entries at their approximate points.
 */
export function PlaceScreen({ geonameId }: { geonameId: number }) {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` counts the retries; each one asks again.
  useEffect(() => {
    let current = true;
    setLoad({ kind: 'loading' });
    void getPlace(geonameId, null).then((result) => {
      if (!current) {
        return;
      }
      if (result.ok) {
        setLoad({
          kind: 'ready',
          place: result.data,
          entries: result.data.entries,
          cursor: result.data.next_cursor,
          more: result.data.next_cursor !== null,
        });
      } else {
        setLoad(result.status === 404 ? { kind: 'missing' } : { kind: 'failed', failure: result });
      }
    });
    return () => {
      current = false;
    };
  }, [geonameId, attempt]);

  const loadMore = async () => {
    /* v8 ignore next: narrows the type; the button exists only while a page is ready with a cursor */
    if (load.kind !== 'ready' || load.cursor === null) {
      return;
    }
    const result = await getPlace(geonameId, load.cursor);
    if (result.ok) {
      setLoad({
        ...load,
        entries: [...load.entries, ...result.data.entries],
        cursor: result.data.next_cursor,
        more: result.data.next_cursor !== null,
      });
    }
  };

  if (load.kind === 'missing') {
    return (
      <StatusScreen
        icon={<AtlasIcon width="28" height="28" />}
        title={A.place.notFound.title}
        description={A.place.notFound.description}
        className="py-16"
      >
        <LinkButton href="/atlas" variant="secondary">
          {A.entry.back}
        </LinkButton>
      </StatusScreen>
    );
  }

  const selectedFeature =
    load.kind === 'ready' ? (load.entries.find((entry) => entry.id === selected) ?? null) : null;
  const label = load.kind === 'ready' ? load.place.place.label : '';

  return (
    <MapLayout
      mapLabel={A.mapLabel}
      mapClassName="hidden tablet:block"
      panel={
        <div className="flex flex-col gap-5 px-4 py-6 tablet:px-5">
          <Link
            href="/atlas"
            className="inline-flex min-h-10 items-center self-start text-link underline-offset-4 hover:underline"
          >
            {A.entry.back}
          </Link>
          {load.kind === 'loading' ? (
            <p role="status" className="m-0 text-fg-muted">
              {A.place.loading}
            </p>
          ) : null}
          {load.kind === 'failed' ? (
            <div role="alert" className="flex flex-col items-start gap-3">
              <Notice tone="error">{failureMessage(load.failure)}</Notice>
              <Button variant="ghost" onClick={() => setAttempt((count) => count + 1)}>
                {A.retry}
              </Button>
            </div>
          ) : null}
          {load.kind === 'ready' ? (
            <>
              <header className="flex flex-col gap-1.5">
                <h1 className="m-0 font-bold font-display text-[2rem] text-gilded leading-[1.3]">
                  {A.place.title(label)}
                </h1>
                <p className="m-0 text-[0.875rem] text-fg-muted">
                  {A.joinLabels([load.place.place.admin_label, load.place.place.country_label])}
                </p>
                <p className="m-0 text-fg-soft leading-[1.85]">{A.place.lead}</p>
              </header>
              {selectedFeature === null ? null : (
                <EntryCard feature={selectedFeature} onClose={() => setSelected(null)} />
              )}
              <ul className="m-0 flex list-none flex-col gap-1 p-0" aria-label={A.list}>
                {load.entries.map((feature) => (
                  <li key={feature.id}>
                    <button
                      type="button"
                      aria-pressed={feature.id === selected}
                      onClick={() => setSelected(feature.id)}
                      className="flex min-h-12 w-full flex-col items-start rounded-[var(--radius-card)] px-3 py-2 text-start transition-colors duration-200 hover:bg-surface aria-pressed:bg-[var(--chip-primary-bg)]"
                    >
                      <span className="font-semibold text-fg">{feature.properties.title}</span>
                      <span className="text-[0.8125rem] text-fg-muted">
                        {feature.properties.glimpse}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              {load.more ? (
                <Button variant="secondary" onClick={() => void loadMore()} className="self-start">
                  {A.place.more}
                </Button>
              ) : (
                <p className="m-0 text-[0.875rem] text-fg-muted">{A.place.end}</p>
              )}
            </>
          ) : null}
        </div>
      }
      map={
        load.kind === 'ready' ? (
          <MapView
            features={load.entries}
            selectedId={selected}
            onSelect={setSelected}
            view={{ center: lngLatOf(load.place.point), zoom: 11 }}
          />
        ) : (
          <div className="h-full bg-surface" />
        )
      }
      className="pb-4 tablet:pb-0"
    />
  );
}
