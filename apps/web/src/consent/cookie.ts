/**
 * The first-party cookies of the consent, read by the page and by the web
 * server (which renders the consent screen already open when it is needed):
 *
 * - `tabsira_consent`: the anonymous consent id the API gave, so the choice is
 *   found again. It holds no choice and nothing about the person; the proof
 *   stays on the server (owner decision 32).
 * - `tabsira_consent_dismissed`: a refusal the API could not record, for this
 *   browser session only, so the question is not put again on every page.
 * - `tabsira_consent_view`: for a visitor without JavaScript, which view of the
 *   screen to show after the form posted (customise, or a failed save); five minutes.
 */

export const CONSENT_COOKIE = 'tabsira_consent';
export const DISMISSED_COOKIE = 'tabsira_consent_dismissed';
export const VIEW_COOKIE = 'tabsira_consent_view';

const ID_SHAPE = /^[A-Za-z0-9_-]{8,128}$/;
/**
 * The id outlives a single choice on purpose: when a choice lapses (a new
 * policy, or reask_days), the API says so for this id and the visitor's new
 * answer joins the same history. 395 days stays under the 400-day cap of
 * current browsers.
 */
export const CONSENT_MAX_AGE_SECONDS = 395 * 86_400;
export const VIEW_MAX_AGE_SECONDS = 300;

export type ConsentView = 'customise' | 'failed';

/** The id, when it has the shape of one. */
export function validConsentId(value: string | undefined | null): string | null {
  return typeof value === 'string' && ID_SHAPE.test(value) ? value : null;
}

export function validView(value: string | undefined | null): ConsentView | null {
  return value === 'customise' || value === 'failed' ? value : null;
}

function cookieValue(name: string, cookies: string): string | null {
  for (const part of cookies.split(';')) {
    const [key, ...value] = part.trim().split('=');
    if (key === name) {
      return decodeURIComponent(value.join('='));
    }
  }
  return null;
}

export function readConsentId(cookies: string = document.cookie): string | null {
  return validConsentId(cookieValue(CONSENT_COOKIE, cookies));
}

export function readDismissed(cookies: string = document.cookie): boolean {
  return cookieValue(DISMISSED_COOKIE, cookies) === '1';
}

/** `; Path=/; …` for a cookie of the page; no Max-Age makes it last the browser session. */
export function cookieAttributes(maxAgeSeconds: number | null, secure: boolean): string {
  const age = maxAgeSeconds === null ? '' : `; Max-Age=${maxAgeSeconds}`;
  return `; Path=/${age}; SameSite=Lax${secure ? '; Secure' : ''}`;
}

function write(name: string, value: string, maxAgeSeconds: number | null): void {
  const secure = window.location.protocol === 'https:';
  // biome-ignore lint/suspicious/noDocumentCookie: the Cookie Store API is still missing from Safari and Firefox; plain first-party cookies need nothing more.
  document.cookie = `${name}=${encodeURIComponent(value)}${cookieAttributes(maxAgeSeconds, secure)}`;
}

export function writeConsentId(id: string): void {
  write(CONSENT_COOKIE, id, CONSENT_MAX_AGE_SECONDS);
}

export function clearConsentId(): void {
  write(CONSENT_COOKIE, '', 0);
}

export function writeDismissed(dismissed: boolean): void {
  write(DISMISSED_COOKIE, dismissed ? '1' : '', dismissed ? null : 0);
}
