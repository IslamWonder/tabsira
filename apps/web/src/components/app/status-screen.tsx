import { type ReactNode, useId } from 'react';
import { Chip } from '@/components/ui/chip';
import { cx } from '@/lib/cx';
import { Beacon } from './beacon';

export interface StatusScreenProps {
  icon: ReactNode;
  title: string;
  description: string;
  /** A short state above the title, e.g. coming soon. */
  badge?: string;
  /** The page's own h1, or a section under another h1. */
  headingLevel?: 1 | 2;
  /** Centred on its own; aligned to the start inside a panel. */
  align?: 'center' | 'start';
  /** Shows the emblem; off when the page draws its own beside it. */
  emblem?: boolean;
  className?: string;
  /** Actions or a follow-up line. */
  children?: ReactNode;
}

/**
 * One calm screen for every state that is not content yet: coming soon, not
 * found, error, offline. One message and at most one way forward (Occam's
 * razor); the cause is never put on the reader (tajriba §7).
 */
export function StatusScreen({
  icon,
  title,
  description,
  badge,
  headingLevel = 1,
  align = 'center',
  emblem = true,
  className,
  children,
}: StatusScreenProps) {
  const titleId = useId();
  const Heading = headingLevel === 1 ? 'h1' : 'h2';
  return (
    <section
      aria-labelledby={titleId}
      className={cx(
        'flex flex-col gap-4',
        align === 'center' ? 'mx-auto max-w-md items-center px-6 text-center' : 'items-start',
        className
      )}
    >
      {emblem ? <Beacon>{icon}</Beacon> : null}
      {badge === undefined ? null : <Chip tone="primary">{badge}</Chip>}
      <Heading id={titleId} className="m-0 font-bold text-[1.75rem] text-gilded">
        {title}
      </Heading>
      <p className="m-0 text-fg-soft leading-[1.9]">{description}</p>
      {children}
    </section>
  );
}
