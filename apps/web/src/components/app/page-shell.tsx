'use client';

import type { ReactNode } from 'react';
import { type ServerConsent, useSeededConsent } from '@/consent/store';

/**
 * The page itself: the bars, the content and the footer. While the cookie
 * choice is open it stays in sight under the wash, but inert and hidden from
 * assistive technology, from the server's first byte (the screen is in the
 * same HTML) until a choice is made. No wrapper transform: fixed bars keep
 * their place (AGENTS.md lessons).
 */
export function PageShell({
  consent,
  children,
}: Readonly<{ consent: ServerConsent; children: ReactNode }>) {
  const { consent: state, settingsOpen } = useSeededConsent(consent);
  const covered = state.status === 'asking' || settingsOpen;
  return (
    <div inert={covered} aria-hidden={covered || undefined}>
      {children}
    </div>
  );
}
