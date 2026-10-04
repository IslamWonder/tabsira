import type { ReactNode } from 'react';
import { cx } from '@/lib/cx';

export type ChipTone = 'neutral' | 'primary' | 'quran' | 'sunnah' | 'glass';

const TONES: Record<ChipTone, string> = {
  neutral: 'border border-line bg-surface text-fg-soft',
  primary:
    'border border-[var(--chip-primary-border)] bg-[var(--chip-primary-bg)] text-[var(--chip-primary-fg)]',
  quran: 'bg-[var(--quran-label-bg)] font-semibold text-[var(--quran-label)]',
  sunnah: 'bg-[var(--sunnah-label-bg)] font-semibold text-[var(--sunnah-label)]',
  // Over a photo: the glass keeps the label legible on its brightest pixels.
  glass: 'glass text-glass-fg-soft',
};

export interface ChipProps {
  tone?: ChipTone;
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** A short static label: a source, a relation, a state. Not interactive. */
export function Chip({ tone = 'neutral', icon, className, children }: ChipProps) {
  return (
    <span
      className={cx(
        'inline-flex min-h-7 items-center gap-1.5 rounded-full px-3 font-medium text-[0.8125rem] leading-none',
        TONES[tone],
        className
      )}
    >
      {icon ? (
        <span aria-hidden="true" className="inline-flex">
          {icon}
        </span>
      ) : null}
      {children}
    </span>
  );
}
