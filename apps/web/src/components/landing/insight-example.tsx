'use client';

import type { Route } from 'next';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { type KeyboardEvent, useEffect, useId, useRef, useState } from 'react';
import { InsightEvidence } from '@/components/insight/insight-evidence';
import { RAIN_PHOTO } from '@/components/scene/rain-scene';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import { cx } from '@/lib/cx';
import { getRainTutorial, keepRainInsight, type Tutorial } from '@/lib/scan/api';
import { journeyFailureMessage } from '@/lib/scan/failure';
import { messages } from '@/messages';

const E = messages.landing.example;

/**
 * The two tabs: the scene's two prepared insights, named by their titles. Each shows
 * its whole pair of texts: its small step may rest on either, so neither is hidden.
 */
const TABS = [
  { id: 'drop', label: (messages.scene.example.insights[0] as { title: string }).title },
  { id: 'planting', label: (messages.scene.example.insights[1] as { title: string }).title },
] as const;

type TabId = (typeof TABS)[number]['id'];

type Load = { status: 'loading' } | { status: 'failed' } | { status: 'ready'; tutorial: Tutorial };

/**
 * The example section (messages.landing.example): the prepared rain scene and its two insights,
 * one per tab (the arrows, Home and End move between them). Each insight's verse
 * and hadith come from the API's prepared scene, through the same cards as an
 * insight, byte for byte, with the API's notice when a hadith waits for its
 * ruling; the reflection and the small step (under the API's own label) stand
 * apart from them, and the label says it is a prepared example, never an
 * analysis. Its open button keeps the tab's own insight, as the scene always
 * has, and opens it.
 */
export function InsightExample() {
  const router = useRouter();
  const baseId = useId();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [load, setLoad] = useState<Load>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [tab, setTab] = useState<TabId>('drop');
  const [opening, setOpening] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` asks again after a failure.
  useEffect(() => {
    const controller = new AbortController();
    setLoad({ status: 'loading' });
    void getRainTutorial(controller.signal).then((result) => {
      if (!controller.signal.aborted) {
        setLoad(result.ok ? { status: 'ready', tutorial: result.data } : { status: 'failed' });
      }
    });
    return () => controller.abort();
  }, [attempt]);

  const choose = (index: number) => {
    const next = TABS[(index + TABS.length) % TABS.length] as (typeof TABS)[number];
    setTab(next.id);
    setOpenError(null);
    tabRefs.current[TABS.indexOf(next)]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const current = TABS.findIndex((item) => item.id === tab);
    // Right to left: the next tab is to the left.
    const moves: Record<string, number> = {
      ArrowLeft: current + 1,
      ArrowRight: current - 1,
      Home: 0,
      End: TABS.length - 1,
    };
    const target = moves[event.key];
    if (target !== undefined) {
      event.preventDefault();
      choose(target);
    }
  };

  const active = TABS.find((item) => item.id === tab) as (typeof TABS)[number];
  const insight =
    load.status === 'ready'
      ? load.tutorial.insights.find((item) => item.slug === active.id)
      : undefined;

  const open = async () => {
    setOpening(true);
    setOpenError(null);
    const result = await keepRainInsight(active.id);
    if (result.ok) {
      router.push(`/insight/${result.data.id}` as Route);
      return;
    }
    setOpening(false);
    setOpenError(journeyFailureMessage(result));
  };

  return (
    <div className="grid gap-6 tablet:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] tablet:items-start">
      <figure className="relative m-0 aspect-[4/5] w-full overflow-hidden rounded-[22px] border border-line tablet:max-h-[560px]">
        <Image
          src={RAIN_PHOTO.src}
          alt={messages.scene.example.alt}
          fill
          sizes="(min-width: 768px) 40vw, 100vw"
          className="object-cover"
        />
      </figure>
      <div className="flex min-w-0 flex-col gap-4">
        <div
          role="tablist"
          aria-label={E.tabs}
          onKeyDown={onKeyDown}
          className="inline-flex self-start rounded-full border border-line bg-surface p-1"
        >
          {TABS.map((item, index) => (
            <button
              key={item.id}
              ref={(element) => {
                tabRefs.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`${baseId}-${item.id}`}
              aria-selected={item.id === tab}
              aria-controls={`${baseId}-panel`}
              tabIndex={item.id === tab ? 0 : -1}
              onClick={() => choose(index)}
              className={cx(
                'min-h-11 rounded-full px-5 font-semibold text-[0.9375rem] transition-colors duration-200',
                item.id === tab
                  ? 'bg-[var(--chip-primary-bg)] text-[var(--chip-primary-fg)]'
                  : 'text-fg-soft hover:text-fg'
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div
          id={`${baseId}-panel`}
          role="tabpanel"
          aria-labelledby={`${baseId}-${tab}`}
          className="flex min-w-0 flex-col gap-4"
        >
          {load.status === 'loading' ? (
            <p role="status" className="m-0 text-fg-soft">
              {E.loading}
            </p>
          ) : null}
          {load.status === 'failed' ? (
            <div className="flex flex-col items-start gap-3">
              <p role="alert" className="m-0 text-fg-soft">
                {E.unavailable}
              </p>
              <Button variant="secondary" onClick={() => setAttempt((count) => count + 1)}>
                {E.retry}
              </Button>
            </div>
          ) : null}
          {load.status === 'ready' && insight !== undefined ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Chip tone="primary">{load.tutorial.label}</Chip>
              </div>
              <h3 className="m-0 font-bold font-display text-[1.75rem] text-gilded leading-[1.45]">
                {insight.title}
              </h3>
              <InsightEvidence insight={insight} headingLevel={3} />
              <section
                aria-label={E.reflection}
                className="flex flex-col gap-1 rounded-[18px] border border-line bg-surface p-4"
              >
                <h4 className="m-0 font-semibold text-[0.875rem] text-fg-soft">{E.reflection}</h4>
                <p className="m-0 text-base text-fg leading-[1.9]">{insight.glimpse}</p>
                {insight.small_step === null ? null : (
                  <p className="m-0 text-[0.9375rem] text-fg-soft leading-[1.9]">
                    <span className="font-semibold text-fg">{insight.small_step.label}: </span>
                    {insight.small_step.text}
                  </p>
                )}
              </section>
              <div className="flex flex-col items-start gap-2">
                <Button onClick={() => void open()} disabled={opening}>
                  {opening ? E.opening : E.open}
                </Button>
                {openError === null ? null : <Notice tone="error">{openError}</Notice>}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
