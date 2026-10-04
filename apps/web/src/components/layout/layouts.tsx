import type { ReactNode } from 'react';
import { cx } from '@/lib/cx';

/*
 * Layout primitives for the responsive web app (DESIGN_DECISION.md «Responsive
 * web application»): phone below 768 px, `tablet:` from 768, `desktop:` from
 * 1200, content at most 1440 px wide and centred. Each primitive puts its
 * parts in the DOM in reading order, start side first, so keyboard and
 * screen-reader order always match what the eye reads in Arabic; only the grid
 * decides where they sit. Heights use --app-height so a full-screen layout
 * also fits inside a gallery preview frame.
 */

const FULL_HEIGHT = 'tablet:h-[calc(var(--app-height)-var(--topbar-height))]';

interface Slot {
  className?: string;
}

/** The page width: gutters on every size, never wider than 1440 px. */
export function PageContainer({ children, className }: Slot & { children: ReactNode }) {
  return (
    <div className={cx('mx-auto w-full max-w-[1440px] px-4 tablet:px-6 desktop:px-10', className)}>
      {children}
    </div>
  );
}

export interface StageLayoutProps extends Slot {
  /** The start-side panel: title, the insights as a list, the new-scene actions. */
  panel: ReactNode;
  /** The photo stage, on the larger side. */
  stage: ReactNode;
  /** Names the stage region for screen readers. */
  stageLabel: string;
  /** Overrides the stage's phone height (full screen by default, for a full-bleed photo). */
  stageClassName?: string;
}

/**
 * Scene and analysis, cinematic: the photo is the stage, the larger side, the
 * full height under the top bar and flush to the edge, melting into the night
 * (or the dawn) toward the panel; the panel holds what to do with it (Law of
 * Common Region: the panel is one group, the stage another). On a phone the
 * two stack, and a page usually keeps only the stage (full bleed).
 */
export function StageLayout({
  panel,
  stage,
  stageLabel,
  stageClassName,
  className,
}: StageLayoutProps) {
  return (
    <div
      className={cx(
        'mx-auto flex w-full max-w-[1440px] flex-col',
        'tablet:grid tablet:grid-cols-[minmax(19rem,2fr)_minmax(0,3fr)]',
        'desktop:grid-cols-[33rem_minmax(0,1fr)]',
        FULL_HEIGHT,
        className
      )}
    >
      <div className="scroll-quiet min-h-0 tablet:overflow-y-auto tablet:px-8 tablet:py-8 desktop:ps-10 desktop:pe-12">
        {panel}
      </div>
      <section
        aria-label={stageLabel}
        className={cx(
          'relative h-[var(--app-height)] min-h-0 overflow-hidden tablet:h-auto',
          stageClassName
        )}
      >
        {stage}
        {/* From tablet up the photo melts into the page on the panel side and at the foot. */}
        <div
          aria-hidden="true"
          className={cx(
            'pointer-events-none absolute inset-0 hidden tablet:block',
            // Toward the panel, which sits on the start side in either direction.
            'bg-[linear-gradient(to_right,var(--stage-fade)_0%,transparent_22%),linear-gradient(to_top,var(--stage-fade)_0%,transparent_14%)]',
            'rtl:bg-[linear-gradient(to_left,var(--stage-fade)_0%,transparent_22%),linear-gradient(to_top,var(--stage-fade)_0%,transparent_14%)]'
          )}
        />
      </section>
    </div>
  );
}

export interface ReadingLayoutProps extends Slot {
  /** The photo, kept in view while reading. */
  media: ReactNode;
  /** The reading column. */
  children: ReactNode;
  /** Actions pinned to the bottom of the reading column (the done button, share). */
  footer?: ReactNode;
}

/**
 * The insight: a 680 px reading column (a comfortable Arabic measure) and the
 * photo beside it, sticky, so the reader never has to remember which scene
 * the text is about (Working memory). On a phone the photo sits on top and
 * fades into the page. The photo comes first in the DOM: it is what the text
 * talks about, and it holds no control.
 */
export function ReadingLayout({ media, children, footer, className }: ReadingLayoutProps) {
  return (
    <div
      className={cx(
        'relative mx-auto flex w-full max-w-[1440px] flex-col',
        'desktop:grid desktop:grid-cols-[minmax(0,680px)_minmax(0,520px)] desktop:justify-center desktop:gap-12 desktop:px-10 desktop:py-8',
        className
      )}
    >
      <div className="desktop:sticky desktop:top-[calc(var(--topbar-height)+2rem)] desktop:col-start-2 desktop:row-start-1 desktop:self-start">
        {media}
      </div>
      {/* Below desktop the text starts over the photo's faded end, as in the phone mockup. */}
      <article className="relative -mt-24 flex min-w-0 flex-col gap-[18px] px-[18px] tablet:px-6 desktop:col-start-1 desktop:row-start-1 desktop:mt-0 desktop:px-0">
        {children}
        {footer === undefined ? null : (
          <div className="sticky bottom-0 z-10 -mx-[18px] bg-[linear-gradient(180deg,transparent,var(--bg)_35%)] px-[18px] pt-4 pb-[max(20px,env(safe-area-inset-bottom))] tablet:-mx-6 tablet:px-6 desktop:mx-0 desktop:px-0">
            {footer}
          </div>
        )}
      </article>
    </div>
  );
}

export interface MapLayoutProps extends Slot {
  /** The list of places or results: the accessible alternative made a feature. */
  panel: ReactNode;
  map: ReactNode;
  mapLabel: string;
  /** Overrides the map's phone height (full screen by default). */
  mapClassName?: string;
}

/** World and atlas: the map fills the main area, the list sits on the start side from tablet up. */
export function MapLayout({ panel, map, mapLabel, mapClassName, className }: MapLayoutProps) {
  return (
    <div
      className={cx(
        'flex w-full flex-col',
        'tablet:grid tablet:grid-cols-[20rem_minmax(0,1fr)] desktop:grid-cols-[24rem_minmax(0,1fr)]',
        FULL_HEIGHT,
        className
      )}
    >
      <aside className="min-h-0 tablet:overflow-y-auto tablet:border-line tablet:border-e">
        {panel}
      </aside>
      <section
        aria-label={mapLabel}
        className={cx('relative h-[var(--app-height)] min-h-0 tablet:h-auto', mapClassName)}
      >
        {map}
      </section>
    </div>
  );
}

export interface FeedLayoutProps extends Slot {
  /** Tabs and filters: on top of the feed on a phone, a side column on a desktop. */
  aside: ReactNode;
  feed: ReactNode;
}

/** Community: one centred column at most 640 px wide, so posts read like a feed, not a grid. */
export function FeedLayout({ aside, feed, className }: FeedLayoutProps) {
  return (
    <div
      className={cx(
        'mx-auto flex w-full max-w-[1440px] flex-col gap-4 px-4 tablet:px-6',
        'desktop:grid desktop:grid-cols-[18rem_minmax(0,40rem)] desktop:justify-center desktop:gap-10 desktop:px-10 desktop:py-8',
        className
      )}
    >
      <div className="desktop:sticky desktop:top-[calc(var(--topbar-height)+2rem)] desktop:self-start">
        {aside}
      </div>
      <div className="mx-auto w-full max-w-[40rem] min-w-0">{feed}</div>
    </div>
  );
}

export interface SettingsLayoutProps extends Slot {
  /** The section list; hidden on a phone, where the sections simply follow each other. */
  nav: ReactNode;
  children: ReactNode;
}

/** Me: a section list on the start side from tablet up, one list on a phone. */
export function SettingsLayout({ nav, children, className }: SettingsLayoutProps) {
  return (
    <div
      className={cx(
        'mx-auto w-full max-w-[1100px] px-4 tablet:grid tablet:grid-cols-[15rem_minmax(0,1fr)] tablet:gap-8 tablet:px-6 tablet:py-8',
        className
      )}
    >
      <div className="hidden tablet:block tablet:sticky tablet:top-[calc(var(--topbar-height)+2rem)] tablet:self-start">
        {nav}
      </div>
      <div className="flex min-w-0 flex-col gap-6">{children}</div>
    </div>
  );
}
