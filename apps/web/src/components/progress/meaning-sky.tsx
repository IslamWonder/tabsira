'use client';

import { getImageProps } from 'next/image';
import Link from 'next/link';
import {
  type ReactNode,
  type RefObject,
  useCallback,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useCapture } from '@/components/capture/capture-provider';
import { OnwardArrowIcon, SparkIcon } from '@/components/icons';
import { insightHref } from '@/components/world/world-model';
import { WorldPanel } from '@/components/world/world-panel';
import { cx } from '@/lib/cx';
import { formatDay } from '@/lib/dates';
import { messages } from '@/messages';
import type { Progress, Star } from '@/progress/api';
import { type Box, LIGHT_OFFSET, type Placement, placeStars } from './sky-layout';

const M = messages.practiceView.sky;

export const SKY_WIDE_SRC = '/practice/meaning-sky-background.webp';
export const SKY_TALL_SRC = '/practice/meaning-sky-background-portrait.webp';

export type SkyState =
  | { status: 'loading' }
  | { status: 'failed'; retry: () => void }
  | { status: 'ready'; sky: Progress['sky']; refreshing?: boolean };

/** The field's size before it can be measured (a test, or a first render with no layout). */
const NOMINAL = { width: 1000, height: 500 };

/**
 * The picture under the sky: a portrait cut on a phone and the whole landscape
 * from tablet up, each at the sizes the image service makes. It is decoration
 * only: hidden from assistive technology, never a target, and the scene's
 * own night colour shows if it is late or never comes.
 */
function SkyArtwork() {
  const common = { alt: '', sizes: '100vw' };
  const {
    props: { srcSet: wide },
  } = getImageProps({ ...common, src: SKY_WIDE_SRC, width: 1536, height: 1024 });
  const {
    props: { srcSet: tall, ...image },
  } = getImageProps({ ...common, src: SKY_TALL_SRC, width: 704, height: 1024 });
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 select-none">
      <picture>
        <source media="(width >= 48rem)" srcSet={wide} sizes={common.sizes} />
        {/* The head of the page: fetched at once, never left to the image service's lazy default. */}
        <img
          {...image}
          srcSet={tall}
          alt=""
          draggable={false}
          loading="eager"
          fetchPriority="high"
          className="absolute inset-0 block size-full object-cover"
        />
      </picture>
    </div>
  );
}

function SceneHeading({
  trail,
  count,
  headingRef,
  countRef,
}: Readonly<{
  trail: ReactNode;
  count: number | null;
  headingRef: RefObject<HTMLDivElement | null>;
  countRef: RefObject<HTMLParagraphElement | null>;
}>) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 pt-5 tablet:px-8 tablet:pt-8 desktop:px-12 desktop:pt-10">
      <div ref={headingRef} className="sky-text-shadow flex shrink-0 flex-col gap-1">
        {trail}
        <h2
          id="practice-sky"
          className="m-0 font-bold font-display text-[30px] text-[var(--sky-text)] leading-[1.3] tablet:text-[44px] desktop:text-[56px] wide:text-[64px]"
        >
          {M.title}
        </h2>
        <p className="m-0 text-[16px] text-[var(--sky-gold)] tablet:text-[19px] desktop:text-[22px]">
          {M.lead}
        </p>
      </div>
      {count === null ? null : (
        <p
          ref={countRef}
          className="sky-text-shadow m-0 flex items-center gap-2 pt-2 text-[15px] leading-[1.5] tablet:pt-3 tablet:text-[16px]"
        >
          <SparkIcon width="16" height="16" className="shrink-0 text-[var(--sky-gold)]" />
          {M.count(count)}
        </p>
      )}
    </div>
  );
}

function StarButton({
  star,
  at,
  measured,
  selected,
  arrived,
  dockId,
  buttonRef,
  onSelect,
}: Readonly<{
  star: Star;
  at: { x: number; y: number } | undefined;
  measured: boolean;
  selected: boolean;
  arrived: boolean;
  dockId: string;
  buttonRef: (element: HTMLButtonElement | null) => void;
  onSelect: () => void;
}>) {
  // Until the field is measured every star waits unseen at its own place; a star with no room stays unseen.
  const shown = measured && at !== undefined;
  return (
    <button
      ref={buttonRef}
      type="button"
      aria-pressed={selected}
      aria-controls={dockId}
      aria-label={M.star(star.concept, M.linked(star.count))}
      data-new={arrived ? 'true' : undefined}
      tabIndex={shown ? undefined : -1}
      onClick={onSelect}
      className={cx(
        'sky-star absolute flex w-max max-w-[9.5rem] -translate-x-1/2 flex-col items-center bg-transparent p-0',
        !shown && 'invisible'
      )}
      // A place in pixels of the field, measured from its left edge in either reading direction.
      style={{
        left: at ? at.x : `${star.x * 100}%`,
        top: at ? at.y - LIGHT_OFFSET : `${star.y * 100}%`,
      }}
    >
      <span aria-hidden="true" className="sky-light">
        <span className="sky-ring" />
        <span className="sky-core" />
      </span>
      <span
        aria-hidden="true"
        className="sky-name sky-text-shadow -mt-1 px-1 text-[15px] tablet:text-[17px] desktop:text-[19px]"
      >
        {star.concept}
      </span>
    </button>
  );
}

function OpenInsights({ star, onList }: Readonly<{ star: Star; onList: () => void }>) {
  const classes =
    'sky-open inline-flex min-h-12 shrink-0 items-center justify-center gap-3 self-stretch rounded-full px-7 font-semibold text-[16px] tablet:self-center tablet:px-8';
  const [only] = star.insights;
  if (only === undefined) {
    return null;
  }
  if (star.insights.length === 1) {
    return (
      <Link href={insightHref(only.id)} className={classes}>
        {M.openOne}
        <OnwardArrowIcon width="20" height="20" />
      </Link>
    );
  }
  return (
    <button type="button" aria-haspopup="dialog" onClick={onList} className={classes}>
      {M.open}
      <OnwardArrowIcon width="20" height="20" />
    </button>
  );
}

/** The chosen meaning, in one pearl row near the foot of the scene (in the page's flow on a phone). */
function SelectedMeaningDock({
  star,
  dockId,
  dockRef,
  onList,
}: Readonly<{
  star: Star;
  dockId: string;
  dockRef: RefObject<HTMLDivElement | null>;
  onList: () => void;
}>) {
  return (
    <div
      ref={dockRef}
      id={dockId}
      className="sky-dock pointer-events-auto flex flex-col gap-4 rounded-[28px] p-5 tablet:w-[clamp(640px,56%,900px)] tablet:flex-row tablet:items-center tablet:gap-6 tablet:rounded-[36px] tablet:px-8 tablet:py-6"
    >
      <div className="flex min-w-0 flex-col tablet:min-w-[9rem] tablet:max-w-[16rem]">
        <span className="sky-dock-soft text-[14px]">{M.chosen}</span>
        <strong className="font-bold text-[24px] leading-[1.45]">{star.concept}</strong>
        <span className="sky-dock-soft text-[14px]">{M.linked(star.count)}</span>
      </div>
      <span aria-hidden="true" className="sky-dock-rule hidden w-px self-stretch tablet:block" />
      <p className="m-0 min-w-0 flex-1 text-[16px] leading-[1.8]">
        {M.about(formatDay(star.first_seen))}
      </p>
      <OpenInsights star={star} onList={onList} />
    </div>
  );
}

function InsightList({ star }: Readonly<{ star: Star }>) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {star.insights.map((insight) => (
        <li key={insight.id}>
          <Link
            href={insightHref(insight.id)}
            className="flex min-h-14 w-full flex-col items-start gap-0.5 rounded-[var(--radius-card)] border border-line bg-surface px-4 py-3 text-start transition-colors duration-200 hover:border-[var(--secondary-border)]"
          >
            <span className="font-semibold text-fg leading-[1.6]">{insight.title}</span>
            <span className="text-[0.875rem] text-fg-muted">{formatDay(insight.completed_at)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function MeaningList({
  stars,
  onPick,
}: Readonly<{ stars: readonly Star[]; onPick: (star: Star) => void }>) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {stars.map((star) => (
        <li key={star.concept}>
          <button
            type="button"
            onClick={() => onPick(star)}
            className="flex min-h-12 w-full items-center justify-between gap-3 rounded-[var(--radius-card)] border border-line bg-surface px-4 py-2 text-start transition-colors duration-200 hover:border-[var(--secondary-border)]"
          >
            <span className="font-semibold text-fg">{star.concept}</span>
            <span className="text-[0.875rem] text-fg-muted">{M.linked(star.count)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** The boxes the stars keep clear of, in pixels of the field: the heading, the counter and the dock. */
function reservedBoxes(field: DOMRect, elements: readonly (HTMLElement | null)[]): Box[] {
  return elements.flatMap((element) => {
    const rect = element?.getBoundingClientRect();
    if (!rect || rect.width === 0) {
      return [];
    }
    return [
      {
        x: rect.left - field.left,
        y: rect.top - field.top,
        width: rect.width,
        height: rect.height,
      },
    ];
  });
}

/** Lays the stars out from the field's real size and each name's real width, again on resize and once the font is in. */
function usePlacement(
  stars: readonly Star[],
  fieldRef: RefObject<HTMLFieldSetElement | null>,
  reservedRefs: readonly RefObject<HTMLElement | null>[]
) {
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const [placement, setPlacement] = useState<Placement | null>(null);

  const layout = useCallback(() => {
    const field = fieldRef.current;
    /* v8 ignore next: narrows the type; the field is drawn with the stars, before any layout runs */
    if (!field) return;
    const rect = field.getBoundingClientRect();
    const size = rect.width > 0 ? { width: rect.width, height: rect.height } : NOMINAL;
    const sizes = stars.map((star) => {
      const button = buttons.current.get(star.concept);
      return {
        key: star.concept,
        x: star.x,
        y: star.y,
        width: button?.offsetWidth || 0,
        height: button?.offsetHeight || 0,
      };
    });
    const reserved = reservedBoxes(
      rect,
      reservedRefs.map((ref) => ref.current)
    );
    setPlacement(placeStars(sizes, size, reserved));
  }, [stars, fieldRef, reservedRefs]);

  useLayoutEffect(() => {
    layout();
    const field = fieldRef.current;
    let live = true;
    void document.fonts?.ready.then(() => {
      if (live) {
        layout();
      }
    });
    if (!field || typeof ResizeObserver === 'undefined') {
      return () => {
        live = false;
      };
    }
    // The heading and the dock are watched too: a longer chosen meaning can make the dock taller.
    const observer = new ResizeObserver(() => layout());
    observer.observe(field);
    for (const ref of reservedRefs) {
      /* v8 ignore next: narrows the type; the heading, the count, the dock and the note are drawn with the stars */
      if (ref.current) observer.observe(ref.current);
    }
    return () => {
      live = false;
      observer.disconnect();
    };
  }, [layout, fieldRef, reservedRefs]);

  const register = useCallback(
    (concept: string) => (element: HTMLButtonElement | null) => {
      if (element) {
        buttons.current.set(concept, element);
      } else {
        buttons.current.delete(concept);
      }
    },
    []
  );

  return { placement, register };
}

/** The meanings that appeared since the scene first showed stars: each lights once, never again. */
function useArrivals(stars: readonly Star[]): ReadonlySet<string> {
  const known = useRef<Set<string> | null>(null);
  const [arrived, setArrived] = useState<ReadonlySet<string>>(new Set());
  useLayoutEffect(() => {
    const names = stars.map((star) => star.concept);
    if (known.current === null) {
      known.current = new Set(names);
      return;
    }
    const seen = known.current;
    const fresh = names.filter((name) => !seen.has(name));
    if (fresh.length > 0) {
      for (const name of fresh) {
        seen.add(name);
      }
      setArrived(new Set(fresh));
    }
  }, [stars]);
  return arrived;
}

function byFirstSeen(a: Star, b: Star): number {
  return a.first_seen.localeCompare(b.first_seen) || a.concept.localeCompare(b.concept);
}

type Panel = 'insights' | 'all' | null;

function StarField({
  sky,
  headingRef,
  countRef,
}: Readonly<{
  sky: Progress['sky'];
  headingRef: RefObject<HTMLDivElement | null>;
  countRef: RefObject<HTMLParagraphElement | null>;
}>) {
  const stars = useMemo(() => [...sky.stars].sort(byFirstSeen), [sky.stars]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [announced, setAnnounced] = useState('');
  const [panel, setPanel] = useState<Panel>(null);
  const dockId = useId();
  const fieldRef = useRef<HTMLFieldSetElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const noteRef = useRef<HTMLParagraphElement>(null);
  const reservedRefs = useMemo(
    () => [headingRef, countRef, dockRef, noteRef],
    [headingRef, countRef]
  );
  const { placement, register } = usePlacement(stars, fieldRef, reservedRefs);
  const arrived = useArrivals(stars);

  // The learner's own choice while it exists, otherwise the meaning learned last.
  const star = stars.find((item) => item.concept === chosen) ?? (stars.at(-1) as Star);
  const unplaced = placement?.unplaced.length ?? 0;

  const choose = (item: Star) => {
    setChosen(item.concept);
    setAnnounced(M.star(item.concept, M.linked(item.count)));
  };

  return (
    <>
      <fieldset
        ref={fieldRef}
        className="relative mx-4 mt-3 h-[440px] min-w-0 border-0 p-0 tablet:absolute tablet:inset-x-[7%] tablet:top-[17%] tablet:bottom-[24%] tablet:m-0 tablet:h-auto"
      >
        <legend className="sr-only">{M.label}</legend>
        {stars.map((item) => (
          <StarButton
            key={item.concept}
            star={item}
            at={placement?.placed.get(item.concept)}
            measured={placement !== null}
            selected={item.concept === star.concept}
            arrived={arrived.has(item.concept)}
            dockId={dockId}
            buttonRef={register(item.concept)}
            onSelect={() => choose(item)}
          />
        ))}
      </fieldset>
      <div className="pointer-events-none flex flex-col items-center gap-3 px-4 pt-2 pb-4 tablet:absolute tablet:inset-x-0 tablet:bottom-[7%] tablet:p-0 tablet:px-8">
        <SelectedMeaningDock
          star={star}
          dockId={dockId}
          dockRef={dockRef}
          onList={() => setPanel('insights')}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-6 tablet:contents">
        {unplaced > 0 ? (
          <button
            type="button"
            aria-haspopup="dialog"
            onClick={() => setPanel('all')}
            className="sky-plain inline-flex min-h-11 items-center rounded-full px-4 text-[15px] tablet:absolute tablet:start-8 tablet:bottom-4 desktop:start-12"
          >
            {M.all(stars.length)}
          </button>
        ) : null}
        <SkyNote noteRef={noteRef} />
      </div>
      <p aria-live="polite" className="sr-only">
        {announced}
      </p>
      <WorldPanel
        open={panel === 'insights'}
        onClose={() => setPanel(null)}
        title={M.panelTitle(star.concept)}
        description={M.panelDescription}
      >
        <InsightList star={star} />
      </WorldPanel>
      <WorldPanel
        open={panel === 'all'}
        onClose={() => setPanel(null)}
        title={M.allTitle}
        description={M.allDescription}
      >
        <MeaningList
          stars={stars}
          onPick={(item) => {
            choose(item);
            setPanel(null);
          }}
        />
      </WorldPanel>
    </>
  );
}

function SkyNote({ noteRef }: Readonly<{ noteRef?: RefObject<HTMLParagraphElement | null> }>) {
  return (
    <p
      ref={noteRef}
      className="sky-text-shadow m-0 flex items-center gap-2 text-[14px] text-[var(--sky-text)] tablet:absolute tablet:end-8 tablet:bottom-4 desktop:end-12"
    >
      <SparkIcon width="14" height="14" className="text-[var(--sky-gold)]" />
      {M.note}
    </p>
  );
}

function EmptySky() {
  const capture = useCapture();
  return (
    <>
      <div className="sky-veil flex flex-col items-start gap-3 px-4 pt-10 pb-8 tablet:absolute tablet:inset-x-0 tablet:top-1/2 tablet:mx-auto tablet:w-fit tablet:-translate-y-1/2 tablet:items-center tablet:px-24 tablet:py-14 tablet:text-center">
        <p className="sky-text-shadow m-0 font-semibold text-[22px] tablet:text-[26px]">
          {M.emptyTitle}
        </p>
        <p className="sky-text-shadow m-0 max-w-[32rem] text-[16px] leading-[1.9] tablet:text-[18px]">
          {M.empty}
        </p>
        <button
          type="button"
          onClick={capture.open}
          className="sky-open mt-2 inline-flex min-h-12 items-center gap-3 rounded-full px-7 font-semibold text-[16px]"
        >
          {M.cta}
          <OnwardArrowIcon width="20" height="20" />
        </button>
      </div>
      <div className="px-4 pb-6 tablet:contents">
        <SkyNote />
      </div>
    </>
  );
}

function SkyMessage({
  state,
}: Readonly<{ state: Extract<SkyState, { status: 'loading' | 'failed' }> }>) {
  return (
    <div className="sky-veil flex flex-col items-start gap-3 px-4 pt-10 pb-10 tablet:absolute tablet:inset-x-0 tablet:top-1/2 tablet:mx-auto tablet:w-fit tablet:-translate-y-1/2 tablet:items-center tablet:px-24 tablet:py-14">
      {state.status === 'loading' ? (
        <p role="status" className="sky-text-shadow m-0 text-[18px]">
          {M.loading}
        </p>
      ) : (
        <>
          <p role="alert" className="sky-text-shadow m-0 text-[18px]">
            {M.unavailable}
          </p>
          <button
            type="button"
            onClick={state.retry}
            className="sky-plain inline-flex min-h-12 items-center rounded-full px-6 font-semibold text-[16px]"
          >
            {messages.practiceView.retry}
          </button>
        </>
      )}
    </div>
  );
}

/**
 * The sky of meanings (DESIGN_DECISION.md «Sky of meanings»): one star for each
 * meaning that appeared in an insight the learner completed, over a night
 * picture that is decoration only. The stars, their names and the dock are
 * real elements laid over it, so nothing is part of the picture. A star is a
 * record of learning, never a score: no lines join them, no star is larger
 * for being repeated, and choosing one records nothing.
 */
export function MeaningSkyScene({
  state,
  trail,
}: Readonly<{ state: SkyState; trail?: ReactNode }>) {
  const headingRef = useRef<HTMLDivElement>(null);
  const countRef = useRef<HTMLParagraphElement>(null);
  const ready = state.status === 'ready';
  return (
    <section
      aria-labelledby="practice-sky"
      // Busy only while a reload keeps the stars on screen; the first load says so in its own status line.
      aria-busy={ready && state.refreshing === true}
      className="sky-scene relative isolate min-h-[420px] overflow-hidden tablet:h-[clamp(680px,calc(var(--app-height)-var(--topbar-height)),900px)]"
    >
      <SkyArtwork />
      <div aria-hidden="true" className="sky-shade pointer-events-none absolute inset-0" />
      <div className="relative flex flex-col tablet:h-full">
        <SceneHeading
          trail={trail}
          count={ready && state.sky.count > 0 ? state.sky.count : null}
          headingRef={headingRef}
          countRef={countRef}
        />
        {state.status !== 'ready' ? <SkyMessage state={state} /> : null}
        {ready && state.sky.stars.length === 0 ? <EmptySky /> : null}
        {ready && state.sky.stars.length > 0 ? (
          <StarField sky={state.sky} headingRef={headingRef} countRef={countRef} />
        ) : null}
      </div>
    </section>
  );
}
