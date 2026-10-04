'use client';

import Link from 'next/link';
import { useEffect, useRef } from 'react';
import { CloseIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { GlassPanel } from '@/components/ui/glass-panel';
import { formatDay } from '@/lib/dates';
import { messages } from '@/messages';
import { TreasureCard } from './treasure-card';
import { insightHref, type RegionView } from './world-model';

const M = messages.world.detail;

function FogBody() {
  return <p className="m-0 text-fg-soft leading-[1.9]">{M.fogBody}</p>;
}

function OpenedBody({
  place,
  domainTitle,
}: {
  place: NonNullable<RegionView['place']>;
  domainTitle: string;
}) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="primary">{domainTitle}</Chip>
        {place.last_visited_at === null ? null : (
          <span className="text-fg-muted text-sm">
            {M.lastVisit(formatDay(place.last_visited_at))}
          </span>
        )}
      </div>
      {place.treasure === null ? null : (
        <TreasureCard key={place.treasure.id} id={place.treasure.id} />
      )}
      {place.insights.length === 0 ? null : (
        <section aria-labelledby={`insights-${place.id}`} className="flex flex-col gap-2">
          <h3 id={`insights-${place.id}`} className="m-0 font-semibold text-fg-soft text-base">
            {M.insights}
          </h3>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {place.insights.map((insight) => (
              <li key={insight.id}>
                <Link
                  href={insightHref(insight.id)}
                  className="glass flex min-h-12 flex-col gap-0.5 rounded-[var(--radius-card)] px-4 py-3 text-fg"
                >
                  <span className="font-semibold">{insight.title}</span>
                  <span className="text-fg-muted text-sm">
                    {M.insightMeta(formatDay(insight.completed_at))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/**
 * What one region holds: under fog, a calm line and nothing about what lies
 * there; once opened, its saved insights as cards that lead to each insight's
 * own screen, and a treasure that is ready. Focus moves here when a region is
 * chosen, so a keyboard or screen-reader user lands on what they asked for.
 */
export function PlaceDetail({ view, onClose }: { view: RegionView; onClose: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const regionId = view.region.id;
  // biome-ignore lint/correctness/useExhaustiveDependencies: focus follows the chosen region, not every render.
  useEffect(() => (heading.current as HTMLHeadingElement).focus(), [regionId]);

  return (
    <GlassPanel
      as="section"
      ornate
      aria-labelledby={`detail-${regionId}`}
      className="flex flex-col gap-3 motion-safe:animate-fade-in"
    >
      <div className="flex items-start justify-between gap-3">
        <h2
          id={`detail-${regionId}`}
          ref={heading}
          tabIndex={-1}
          className="m-0 font-bold font-display text-[1.5rem] text-gilded outline-none"
        >
          {view.region.name}
        </h2>
        <Button variant="icon" label={M.back} onClick={onClose}>
          <CloseIcon />
        </Button>
      </div>
      {view.place === null ? (
        <FogBody />
      ) : (
        <OpenedBody place={view.place} domainTitle={view.region.domain_title} />
      )}
    </GlassPanel>
  );
}
