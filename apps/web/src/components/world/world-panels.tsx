'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { openConsentSettings } from '@/consent/store';
import { formatDay } from '@/lib/dates';
import { messages } from '@/messages';
import { type Place, visitPlace } from '@/world/api';
import { LearnedInsight } from './learned-insight';
import { TreasureCard } from './treasure-card';
import type { Learned } from './world-model';

const M = messages.world;

/**
 * What a landmark opens: the chosen insight of its place (the latest learned
 * there unless one was chosen), the place's treasure when it is ready, and the
 * other insights learned there. Opening it records the visit, which is how a
 * treasure knows the learner came back (v2 §17).
 */
export function PlaceContent({
  place,
  insightId,
  onChoose,
  onGoTo,
  onVisited,
}: {
  place: Place;
  insightId: string | null;
  onChoose: (insightId: string) => void;
  onGoTo: (insightId: string) => void;
  onVisited: (place: Place) => void;
}) {
  const chosen = insightId ?? place.insights.at(-1)?.id ?? null;
  const others = place.insights.filter((item) => item.id !== chosen).reverse();
  const placeId = place.id;

  // biome-ignore lint/correctness/useExhaustiveDependencies: one visit per place opened, not per render.
  useEffect(() => {
    void visitPlace(placeId).then((result) => {
      if (result.ok) {
        onVisited(result.data);
      }
    });
  }, [placeId]);

  return (
    <div className="flex flex-col gap-6">
      {chosen === null ? null : (
        <LearnedInsight key={chosen} id={chosen} onGoTo={() => onGoTo(chosen)} />
      )}
      {place.treasure === null ? null : (
        <TreasureCard key={place.treasure.id} id={place.treasure.id} />
      )}
      {others.length === 0 ? null : (
        <section aria-labelledby={`others-${placeId}`} className="flex flex-col gap-2">
          <h3 id={`others-${placeId}`} className="m-0 font-semibold text-base text-fg-soft">
            {M.panel.others}
          </h3>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {others.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onChoose(item.id)}
                  className="flex min-h-12 w-full flex-col items-start gap-0.5 rounded-[var(--radius-card)] border border-line bg-surface px-4 py-2.5 text-start transition-colors duration-200 hover:border-[var(--secondary-border)]"
                >
                  <span className="font-semibold text-fg">{item.title}</span>
                  <span className="text-[0.875rem] text-fg-muted">
                    {M.panel.learnedOn(formatDay(item.completed_at))}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** The learner's list (messages.world.mine): every learned insight, the latest first, reachable without moving the picture. */
export function MineContent({
  items,
  onPick,
}: {
  items: readonly Learned[];
  onPick: (item: Learned) => void;
}) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {items.map((item) => (
        <li key={item.insight.id}>
          <button
            type="button"
            onClick={() => onPick(item)}
            className="flex min-h-14 w-full flex-col items-start gap-0.5 rounded-[var(--radius-card)] border border-line bg-surface px-4 py-3 text-start transition-colors duration-200 hover:border-[var(--secondary-border)]"
          >
            <span className="font-semibold text-fg leading-[1.6]">{item.insight.title}</span>
            <span className="text-[0.875rem] text-fg-muted">
              {M.mineView.item(item.place.name, formatDay(item.insight.completed_at))}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

const PAGES = [
  ['/terms', messages.footer.terms],
  ['/privacy', messages.footer.privacy],
  ['/support', messages.footer.support],
] as const;

/**
 * How the world works, on request only (never opened by itself). The world
 * fills the screen, so the site's pages the footer links elsewhere are here.
 */
export function HelpContent({ onLeave }: { onLeave: () => void }) {
  return (
    <div className="flex flex-col gap-5">
      <ul className="m-0 flex flex-col gap-2.5 ps-5 text-[0.9375rem] text-fg leading-[1.9]">
        {M.helpView.items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <nav aria-label={M.helpView.pages} className="border-line border-t pt-3">
        <ul className="m-0 flex list-none flex-wrap gap-x-5 p-0">
          {PAGES.map(([href, label]) => (
            <li key={href}>
              <Link
                href={href}
                className="inline-flex min-h-12 items-center text-fg-soft text-sm underline-offset-4 hover:text-fg hover:underline"
              >
                {label}
              </Link>
            </li>
          ))}
          <li>
            <button
              type="button"
              aria-haspopup="dialog"
              onClick={() => {
                // The cookie choice is a dialog of its own: this one closes first.
                onLeave();
                openConsentSettings();
              }}
              className="inline-flex min-h-12 items-center text-fg-soft text-sm underline-offset-4 hover:text-fg hover:underline"
            >
              {messages.footer.cookieSettings}
            </button>
          </li>
        </ul>
      </nav>
    </div>
  );
}
