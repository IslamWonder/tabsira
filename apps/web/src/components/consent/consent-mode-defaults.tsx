import { connection } from 'next/server';
import type { ReactElement } from 'react';
import { gaMeasurementId } from '@/config/server-env';
import { CONSENT_MODE_DEFAULTS } from '@/consent/consent-mode';

/**
 * The Consent Mode v2 defaults for <head>, first of all scripts, only when
 * GA_MEASUREMENT_ID is set on the server. `connection()` makes the value a
 * request-time read: a build never decides it. No Google script is loaded
 * here; the tag itself will come later, behind `<ConsentGate>`.
 */
export async function consentModeDefaults(): Promise<ReactElement | null> {
  await connection();
  if (gaMeasurementId() === null) {
    return null;
  }
  const defaults = { __html: CONSENT_MODE_DEFAULTS };
  // biome-ignore lint/security/noDangerouslySetInnerHtml: a constant written in src/consent/consent-mode.ts, with no input from the request or the visitor; it must run before any other script.
  return <script id="consent-mode-defaults" dangerouslySetInnerHTML={defaults} />;
}
