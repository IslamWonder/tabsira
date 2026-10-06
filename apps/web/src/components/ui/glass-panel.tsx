import type { HTMLAttributes, ReactNode } from 'react';
import { OrnateCorners } from '@/components/fx/ornate-corners';
import { cx } from '@/lib/cx';

export type GlassTone = 'neutral' | 'quran' | 'sunnah' | 'primary';

const TONES: Record<GlassTone, string> = {
  neutral: 'shadow-[var(--panel-shadow)]',
  quran: 'shadow-[var(--quran-glow)] border-[var(--quran-border)]',
  sunnah: 'shadow-[var(--sunnah-glow)] border-[var(--sunnah-border)]',
  primary: 'shadow-[var(--primary-glow)] border-[var(--chip-primary-border)]',
};

export interface GlassPanelProps extends HTMLAttributes<HTMLElement> {
  /** The element: a region with a heading is a section, a self-contained item an article. */
  as?: 'div' | 'section' | 'article' | 'aside';
  tone?: GlassTone;
  /** Inner padding; off for content that brings its own (a photo, a list). */
  padded?: boolean;
  /** An RPG window: a gold double rule and khatam corners (DESIGN_DECISION.md «Game feel»). */
  ornate?: boolean;
  children: ReactNode;
}

/**
 * A frosted surface over the night stage or a photo. Law of Common Region: what
 * belongs together sits inside one panel, so the panel itself is the grouping.
 */
export function GlassPanel({
  as: Element = 'div',
  tone = 'neutral',
  padded = true,
  ornate = false,
  className,
  children,
  ...rest
}: Readonly<GlassPanelProps>) {
  return (
    <Element
      className={cx(
        'glass rounded-[var(--radius-panel)]',
        TONES[tone],
        padded && 'p-5',
        ornate && 'fx-ornate fx-ornate-glow border-transparent',
        className
      )}
      {...rest}
    >
      {ornate ? <OrnateCorners /> : null}
      {children}
    </Element>
  );
}
