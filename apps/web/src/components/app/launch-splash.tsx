'use client';

import { useEffect } from 'react';
import { LogoMark } from '@/components/brand/logo';
import { LogoLight } from '@/components/brand/logo-light';
import { messages } from '@/messages';
import { LAUNCH_ATTRIBUTE, LAUNCH_FADE_MS, LAUNCH_MS } from '@/pwa/launch';

function end() {
  document.documentElement.removeAttribute(LAUNCH_ATTRIBUTE);
}

/**
 * The installed app's opening on a phone (DESIGN_DECISION.md «Launch splash»):
 * the night ground of the system splash, the logo written in full screen with
 * its ring and sparks, the tagline, then a fade to the page. It is in every
 * page and shown only while <html> carries `data-launch`, set before the first
 * paint by LAUNCH_SCRIPT; a tap ends it at once. Decorative: screen readers
 * read the page beneath.
 */
export function LaunchSplash() {
  useEffect(() => {
    if (!document.documentElement.hasAttribute(LAUNCH_ATTRIBUTE)) {
      return;
    }
    const timer = setTimeout(end, LAUNCH_MS + LAUNCH_FADE_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    // A tap anywhere skips the opening; it is never focusable and ends by itself.
    <div aria-hidden="true" className="launch-splash" onClick={end} data-testid="launch-splash">
      <span className="relative">
        <LogoLight spark="size-2" />
        <LogoMark className="launch-mark relative h-40" entrance />
      </span>
      <p className="launch-tagline m-0 font-display text-[1.75rem]">{messages.brand.tagline}</p>
    </div>
  );
}
