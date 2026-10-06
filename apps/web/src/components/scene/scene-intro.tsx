import type { ReactNode } from 'react';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

/**
 * The start of the scene panel: an optional state chip (a documented prepared example),
 * the promise as the page's title, and one line on what the app does. Short on
 * purpose: the photo beside it is the subject (Selective attention).
 */
export function SceneIntro({
  chip,
  className,
}: Readonly<{ chip?: ReactNode; className?: string }>) {
  return (
    <div className={cx('flex flex-col items-start gap-3', className)}>
      {chip}
      <h1 className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg">
        {messages.brand.tagline}
      </h1>
      <p className="m-0 text-fg-soft leading-[1.85]">{messages.brand.promise}</p>
    </div>
  );
}
