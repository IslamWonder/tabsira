'use client';

import Link from 'next/link';
import { useId } from 'react';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { insightHref, type RegionView, type Thread } from './world-model';

const M = messages.world.threads;

function titleOf(views: readonly RegionView[], id: string): string | null {
  for (const view of views) {
    const found = view.place?.insights.find((insight) => insight.id === id);
    if (found) {
      return found.title;
    }
  }
  return null;
}

function ThreadItem({
  thread,
  views,
  open,
  onToggle,
}: {
  thread: Thread;
  views: readonly RegionView[];
  open: boolean;
  onToggle: () => void;
}) {
  const panelId = useId();
  const { relation } = thread;
  const insights = relation.insight_ids.flatMap((id) => {
    const title = titleOf(views, id);
    return title === null ? [] : [{ id, title }];
  });
  return (
    <li className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-line bg-surface p-3">
      <p className="m-0 text-fg text-sm">
        {M.between(thread.from.region.name, thread.to.region.name)}
      </p>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
        className={cx(
          'min-h-12 self-start rounded-full border px-4 font-medium text-sm',
          open
            ? 'border-[var(--primary)] bg-[var(--chip-primary-bg)] text-[var(--chip-primary-fg)]'
            : 'border-[var(--secondary-border)] text-[var(--secondary-fg)]'
        )}
      >
        {relation.question}
      </button>
      <div id={panelId} hidden={!open} className="flex flex-col gap-2">
        <p className="m-0 text-fg-soft leading-[1.8]">{relation.reason_label}</p>
        {insights.length === 0 ? null : (
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {insights.map((insight) => (
              <li key={insight.id}>
                <Link
                  href={insightHref(insight.id)}
                  className="inline-flex min-h-12 items-center text-link underline-offset-4 hover:underline"
                >
                  {insight.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

/**
 * The threads: a relation between two places appears only when one is
 * recorded, with the API's own question opening its reason.
 * Opening one draws it stronger on the map.
 */
export function ThreadList({
  threads,
  views,
  active,
  onActive,
}: {
  threads: readonly Thread[];
  views: readonly RegionView[];
  active: string | null;
  onActive: (key: string | null) => void;
}) {
  return (
    <section aria-labelledby="world-threads" className="flex flex-col gap-2">
      <h2 id="world-threads" className="m-0 font-semibold text-base text-fg-soft">
        {M.title}
      </h2>
      <p className="m-0 text-fg-muted text-sm leading-[1.8]">
        {threads.length === 0 ? M.none : M.lead}
      </p>
      {threads.length === 0 ? null : (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {threads.map((thread) => (
            <ThreadItem
              key={thread.key}
              thread={thread}
              views={views}
              open={thread.key === active}
              onToggle={() => onActive(thread.key === active ? null : thread.key)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
