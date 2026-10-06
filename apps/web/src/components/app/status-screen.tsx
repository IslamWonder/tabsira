import { type ReactNode, useId } from 'react';
import { Logo } from '@/components/brand/logo';
import { Chip } from '@/components/ui/chip';
import { GuideScene, type GuideSceneName } from '@/components/ui/guide-scene';
import { cx } from '@/lib/cx';
import { Beacon } from './beacon';

export interface StatusScreenProps {
  /** The state's icon, inside the beacon. */
  icon?: ReactNode;
  title: string;
  description: string;
  /** A short state above the title, e.g. coming soon. */
  badge?: string;
  /** The page's own h1, or a section under another h1. */
  headingLevel?: 1 | 2;
  /** Centred on its own; aligned to the start inside a panel. */
  align?: 'center' | 'start';
  /**
   * Above the title: the beacon around the icon, the full logo for the
   * screens that stand alone (not found, offline, an error), or nothing when
   * the page draws its own beside it.
   */
  emblem?: 'beacon' | 'logo' | 'none';
  /** One of the scenes of guidance instead of the emblem: for what is missing or failed. */
  scene?: GuideSceneName;
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
  emblem = 'beacon',
  scene,
  className,
  children,
}: Readonly<StatusScreenProps>) {
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
      {scene === undefined ? null : <GuideScene scene={scene} size={128} />}
      {scene === undefined && emblem === 'beacon' ? <Beacon>{icon}</Beacon> : null}
      {scene === undefined && emblem === 'logo' ? <Logo className="mb-2 h-32" /> : null}
      {badge === undefined ? null : <Chip tone="primary">{badge}</Chip>}
      <Heading
        id={titleId}
        className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg"
      >
        {title}
      </Heading>
      <p className="m-0 text-fg-soft leading-[1.9]">{description}</p>
      {children}
    </section>
  );
}
