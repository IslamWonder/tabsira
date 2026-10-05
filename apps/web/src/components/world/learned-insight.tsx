'use client';

import { useEffect, useState } from 'react';
import { CheckIcon, ExternalIcon } from '@/components/icons';
import { EngineLabel } from '@/components/insight/engine-label';
import { Button, LinkButton } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { formatDay } from '@/lib/dates';
import { getInsight, type Insight } from '@/lib/scan/api';
import { messages } from '@/messages';
import { insightHref } from './world-model';

const M = messages.world.panel;

type Load = { status: 'loading' } | { status: 'failed' } | { status: 'ready'; insight: Insight };

/**
 * The verse and the hadith by reference, numbered as the insight's own screen numbers
 * them; their text is there. A hadith shown before its ruling says so, with the way to
 * check it on dorar.net beside the line (decision 58).
 */
function Sources({ insight }: { insight: Insight }) {
  const { quran, hadith } = insight;
  if (quran === null && hadith === null) {
    return null;
  }
  return (
    <section aria-label={M.sources} className="flex flex-col gap-1.5">
      <h4 className="m-0 font-semibold text-[0.875rem] text-fg-soft">{M.sources}</h4>
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[0.9375rem] leading-[1.8]">
        {quran === null ? null : (
          <li className="flex flex-wrap items-center gap-2">
            <Chip tone="quran">{quran.tag}</Chip>
            <span>{M.quranReference(quran.verse.surah_name, quran.verse.ayah)}</span>
          </li>
        )}
        {hadith === null ? null : (
          <li className="flex flex-col gap-1">
            <span className="flex flex-wrap items-center gap-2">
              <Chip tone="sunnah">{hadith.tag}</Chip>
              <span>
                {M.hadithReference(hadith.hadith.collection.name_ar, hadith.hadith.number)}
              </span>
            </span>
            {hadith.hadith.ruling === null ? (
              <span className="flex flex-wrap items-center gap-x-3 text-[0.8125rem] text-fg-muted">
                <span>{messages.evidence.unruled}</span>
                <a
                  href={hadith.hadith.links.dorar_verification}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex min-h-12 items-center gap-1.5 font-medium text-link underline-offset-4 hover:underline"
                >
                  {messages.evidence.verifyDorar}
                  <span className="sr-only"> {messages.a11y.opensInNewTab}</span>
                  <ExternalIcon width="16" height="16" />
                </a>
              </span>
            ) : null}
          </li>
        )}
      </ul>
    </section>
  );
}

/**
 * One learned insight in the world's panel (decision 59): its title, its
 * meaning, its sources by reference, its small step and the day it was
 * learned, read from the API when the panel opens. Its open link leads to its
 * own screen, where the texts and the conversation are.
 */
export function LearnedInsight({ id, onGoTo }: { id: string; onGoTo: () => void }) {
  const [load, setLoad] = useState<Load>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` asks again after a failure.
  useEffect(() => {
    let live = true;
    setLoad({ status: 'loading' });
    void getInsight(id).then((result) => {
      if (live) {
        setLoad(result.ok ? { status: 'ready', insight: result.data } : { status: 'failed' });
      }
    });
    return () => {
      live = false;
    };
  }, [id, attempt]);

  if (load.status === 'loading') {
    return (
      <p role="status" className="m-0 py-4 text-fg-soft">
        {M.loading}
      </p>
    );
  }
  if (load.status === 'failed') {
    return (
      <div className="flex flex-col items-start gap-3 py-2">
        <p role="alert" className="m-0 text-fg-soft">
          {M.failed}
        </p>
        <Button variant="secondary" onClick={() => setAttempt((count) => count + 1)}>
          {M.retry}
        </Button>
      </div>
    );
  }
  const { insight } = load;
  return (
    <article aria-labelledby={`learned-${insight.id}`} className="flex flex-col gap-4">
      {/* A prepared example or a simulation says so here too: never shown as live analysis. */}
      <EngineLabel engine={insight.engine} label={insight.label} />
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="primary" icon={<CheckIcon width="14" height="14" />}>
          {M.learned}
        </Chip>
        {insight.completed_at === null ? null : (
          <span className="text-[0.875rem] text-fg-muted">
            {M.learnedOn(formatDay(insight.completed_at))}
          </span>
        )}
      </div>
      <h3
        id={`learned-${insight.id}`}
        className="m-0 font-bold font-display text-[1.625rem] text-gilded leading-[1.45]"
      >
        {insight.title}
      </h3>
      <section aria-label={M.meaning} className="flex flex-col gap-1">
        <h4 className="m-0 font-semibold text-[0.875rem] text-fg-soft">{M.meaning}</h4>
        <p className="m-0 text-base text-fg leading-[1.9]">{insight.glimpse}</p>
      </section>
      <Sources insight={insight} />
      {insight.small_step === null ? null : (
        <section aria-label={M.step} className="flex flex-col gap-1">
          <h4 className="m-0 font-semibold text-[0.875rem] text-fg-soft">{M.step}</h4>
          <p className="m-0 text-[0.9375rem] text-fg leading-[1.9]">{insight.small_step.text}</p>
        </section>
      )}
      <div className="flex flex-col gap-2.5 pt-1">
        <LinkButton href={insightHref(insight.id)}>{M.open}</LinkButton>
        <div className="flex flex-wrap gap-2.5">
          <Button variant="secondary" onClick={onGoTo} className="flex-1">
            {M.goTo}
          </Button>
          {/* A completed insight's conversation is closed; nothing to offer then. */}
          {insight.chat.enabled && !insight.chat.closed ? (
            <LinkButton href={insightHref(insight.id)} variant="ghost" className="flex-1">
              {M.chat}
            </LinkButton>
          ) : null}
        </div>
      </div>
    </article>
  );
}
