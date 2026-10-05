'use client';

import type { Route } from 'next';
import type { LegalVersions } from '@/account/legal';
import { rememberTick } from '@/account/legal-tick';
import { googleStartUrl } from '@/account/links';
import { useGoogleAvailable } from '@/account/providers';
import { OrnamentDivider } from '@/components/fx/ornament-divider';
import { GoogleIcon } from '@/components/icons';
import { buttonClasses } from '@/components/ui/button';
import { messages } from '@/messages';

export interface GoogleSignInProps {
  next: Route;
  /**
   * From the sign-up view: the texts the reader has accepted, or null while
   * the box is unticked, which keeps the button disabled (owner decision 35).
   * The tick is kept in this tab for the way back from Google; it never goes
   * into the link. From the sign-in view: left out (the gate asks afterwards).
   */
  accepted?: LegalVersions | null;
  /** The full-name box of the sign-up view, carried with the tick (decision 64). */
  publicFullName?: boolean;
  /** The ornament that separates it from the e-mail form: under it (sign-in) or above it (sign-up). */
  divider: 'after' | 'before';
}

function Label() {
  return (
    <>
      <GoogleIcon width="20" height="20" />
      <span>
        {messages.auth.google.action} <bdi>{messages.auth.google.name}</bdi>
      </span>
    </>
  );
}

/**
 * «Continue with Google», shown only when the API says Google sign-in is
 * configured. A link: the API route sends the browser on to Google and back
 * (docs/AUTH.md). Until the terms are accepted on the sign-up view it is a
 * disabled button that says the same.
 */
export function GoogleSignIn({
  next,
  accepted,
  publicFullName = false,
  divider,
}: GoogleSignInProps) {
  const available = useGoogleAvailable();
  if (available !== true) {
    return null;
  }
  const classes = buttonClasses('secondary', 'md', 'w-full');
  const button =
    accepted === null ? (
      <button type="button" disabled className={classes}>
        <Label />
      </button>
    ) : (
      <a
        href={googleStartUrl(next)}
        onClick={
          accepted === undefined
            ? undefined
            : () => rememberTick(accepted, Date.now(), publicFullName)
        }
        className={classes}
      >
        <Label />
      </a>
    );
  return divider === 'after' ? (
    <>
      {button}
      <OrnamentDivider label={messages.auth.google.divider} />
    </>
  ) : (
    <>
      <OrnamentDivider label={messages.auth.google.or} />
      {button}
    </>
  );
}
