'use client';

import type { Route } from 'next';
import Image, { type StaticImageData } from 'next/image';
import Link from 'next/link';
import { type ReactNode, useState } from 'react';
import { ShareIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { SoundToggle } from '@/components/ui/sound-toggle';
import { cx } from '@/lib/cx';
import { useBoxSize } from '@/lib/use-box-size';
import { messages } from '@/messages';
import { DoneButton, type DoneStatus } from './done-button';
import { coverPlacement, isRatio } from './scene-geometry';

/*
 * The pieces of the insight page (tajriba §6 order; DESIGN_DECISION.md
 * «Responsive web application»), placed by ReadingLayout: the photo, sticky
 * beside a 680 px reading column from 1200 px, on top and fading into the page
 * below that, as in the phone mockup.
 */

export function BackArrow() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {/* Back points to the start side: right, in Arabic. */}
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

export interface InsightPhotoProps {
  src: string | StaticImageData;
  alt: string;
  width: number;
  height: number;
  /** The point this insight is about, highlighted on the photo. */
  focus?: { x: number; y: number; title: string };
  /** Below desktop the way back sits on the photo, as in the phone mockup. */
  backHref: Route;
  unoptimized?: boolean;
}

export function InsightPhoto({
  src,
  alt,
  width,
  height,
  focus,
  backHref,
  unoptimized = false,
}: Readonly<InsightPhotoProps>) {
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const size = useBoxSize(box);
  const shown = focus !== undefined && isRatio(focus.x) && isRatio(focus.y) ? focus : undefined;
  const placement =
    shown === undefined ? undefined : coverPlacement(shown, { width, height }, size);

  return (
    <figure className="m-0 flex flex-col gap-3">
      <div
        ref={setBox}
        className="relative h-[330px] overflow-hidden tablet:h-[420px] desktop:h-[min(720px,calc(var(--app-height)-var(--topbar-height)-6rem))] desktop:rounded-[28px] desktop:shadow-[var(--stage-shadow)]"
      >
        <Image
          src={src}
          alt={alt}
          fill
          sizes="(min-width: 75rem) 520px, 100vw"
          unoptimized={unoptimized}
          className="object-cover"
        />
        <Link
          href={backHref}
          aria-label={messages.insight.back}
          className="glass absolute top-3.5 start-3.5 z-10 inline-flex size-12 items-center justify-center rounded-full text-glass-fg desktop:hidden"
        >
          <BackArrow />
        </Link>
        {/* The top bar carries the sound switch from tablet up; the photo carries it on a phone. */}
        <SoundToggle className="absolute top-3.5 end-3.5 z-10 tablet:hidden" />
        {/* Below desktop the photo fades into the page, as in the phone mockup. */}
        <div
          aria-hidden="true"
          className="photo-scrim pointer-events-none absolute inset-0 desktop:hidden"
        />
        {shown === undefined || placement === undefined || !placement.visible ? null : (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute flex items-center gap-2.5"
            style={{
              left: `${placement.left}%`,
              top: `${placement.top}%`,
              transform: 'translate(-9px, -50%)',
            }}
          >
            <span
              className="size-[18px] shrink-0 rounded-full"
              style={{
                background: 'var(--point-gold-core)',
                boxShadow:
                  '0 0 0 4px var(--point-ring), 0 0 0 12px color-mix(in srgb, var(--point-gold-halo) 60%, transparent)',
              }}
            />
            <span className="glass hidden h-9 items-center rounded-full px-3.5 font-semibold text-[0.9375rem] text-glass-fg desktop:inline-flex">
              {shown.title}
            </span>
          </span>
        )}
      </div>
      <figcaption className="sr-only desktop:not-sr-only desktop:px-1 desktop:text-[0.8125rem] desktop:text-fg-muted">
        {messages.insight.photoCaption}
      </figcaption>
    </figure>
  );
}

export interface InsightHeaderProps {
  backHref: Route;
  /** The relation and the state, e.g. the relation and the prepared-example state. */
  chips?: ReactNode;
  title: string;
  glimpse: string;
}

/**
 * Title and glimpse first (tajriba §6.1). The way back is always visible: on
 * the desktop as a text link here, below it as the round button on the photo.
 */
export function InsightHeader({ backHref, chips, title, glimpse }: Readonly<InsightHeaderProps>) {
  return (
    <header className="flex flex-col gap-2 desktop:gap-3">
      <Link
        href={backHref}
        className="hidden min-h-10 items-center gap-1.5 self-start text-link desktop:inline-flex"
      >
        <BackArrow />
        {messages.insight.back}
      </Link>
      {chips === undefined ? null : (
        <div className="flex flex-wrap items-center gap-2">{chips}</div>
      )}
      <h1 className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg">
        {title}
      </h1>
      <p className="m-0 text-[1.0625rem] text-fg-soft leading-[1.85] desktop:text-lg">{glimpse}</p>
    </header>
  );
}

/** What the photo shows, kept apart from any interpretation (tajriba §3.8). */
export function SeenNote({ text }: Readonly<{ text: string }>) {
  return (
    <p className="m-0 rounded-[var(--radius-card)] border border-line bg-surface px-4 py-3 text-[0.9375rem] text-fg-soft leading-[1.75]">
      <strong className="font-medium text-fg">{messages.insight.seen}</strong> {text}
    </p>
  );
}

/** The platform's own explanation, labelled as such (the platform explanation label), never mixed with the sources. */
export function ExplanationBlock({ text }: Readonly<{ text: string }>) {
  return (
    <section aria-label={messages.insight.explanation} className="flex flex-col items-start gap-2">
      <Chip tone="primary">{messages.insight.explanation}</Chip>
      <p className="m-0 text-[1.0625rem] text-fg leading-[1.9]">{text}</p>
    </section>
  );
}

export interface InsightToolsProps {
  onWhy: () => void;
  onDiscuss: () => void;
  /** How much of the chat is used, e.g. used 1 of 3; the plain limit before it is known. */
  discussNote?: string;
}

/** Why-this and the chat, side by side from tablet up: two secondary paths, same weight. */
export function InsightTools({
  onWhy,
  onDiscuss,
  discussNote = messages.insight.discussLimit,
}: Readonly<InsightToolsProps>) {
  return (
    <div className="flex flex-col gap-3 tablet:flex-row">
      <button
        type="button"
        aria-haspopup="dialog"
        onClick={onWhy}
        className="flex min-h-[52px] flex-1 items-center justify-between rounded-[var(--radius-card)] border border-line bg-surface px-4 text-[0.96875rem] text-fg transition-colors duration-200 hover:border-[var(--focus)]"
      >
        {messages.insight.why}
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          focusable="false"
          className="text-fg-soft"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      <button
        type="button"
        aria-haspopup="dialog"
        onClick={onDiscuss}
        className="flex min-h-[52px] flex-1 items-center gap-2.5 rounded-[var(--radius-card)] bg-[var(--chip-primary-bg)] px-4 text-[0.96875rem] text-[var(--chip-primary-fg)] transition-colors duration-200 hover:bg-[var(--sunnah-surface-from)]"
      >
        {messages.insight.discuss}
        <span className="ms-auto text-[0.8125rem] text-fg-soft">{discussNote}</span>
      </button>
    </div>
  );
}

export interface InsightActionsProps {
  status?: DoneStatus;
  onDone: () => void;
  /** Left out when the insight cannot be shared: then there is no share button. */
  onShare?: () => void;
}

/** the done button and sharing at the end of the reading column (Fitts: in the thumb zone on a phone). */
export function InsightActions({ status, onDone, onShare }: Readonly<InsightActionsProps>) {
  return (
    <div className="flex items-center gap-2.5">
      <DoneButton status={status} onDone={onDone} className="flex-1" />
      {onShare === undefined ? null : (
        <Button
          variant="secondary"
          size="lg"
          onClick={onShare}
          className={cx('px-0 tablet:px-6', 'size-14 tablet:size-auto')}
        >
          <ShareIcon />
          <span className="sr-only tablet:not-sr-only">{messages.insight.share}</span>
        </Button>
      )}
    </div>
  );
}
