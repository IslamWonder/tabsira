import type { ReactNode } from 'react';
import { messages } from '@/messages';

/**
 * The start of the scene panel: an optional state chip (a documented prepared example),
 * the promise as the page's title, and one line on what the app does. Short on
 * purpose: the photo beside it is the subject (Selective attention).
 */
export function SceneIntro({ chip }: { chip?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-4">
      {chip}
      <h1 className="m-0 font-bold font-display text-[2.25rem] text-gilded leading-[1.3] desktop:text-[3rem]">
        {messages.brand.tagline}
      </h1>
      <p className="m-0 text-[1.0625rem] text-fg-soft leading-[1.85] desktop:text-lg">
        {messages.brand.promise}
      </p>
    </div>
  );
}
