import type { Route } from 'next';
import { apiOrigin } from '@/lib/site';

/** Where a sign-in lands when nothing else was asked for. */
export const DEFAULT_LANDING: Route = '/me';
const NEXT_MAX = 512;

function hasControlCharacter(text: string): boolean {
  return Array.from(text).some((char) => {
    const code = char.charCodeAt(0);
    return code < 0x20 || code === 0x7f;
  });
}

/**
 * A `?next=` value made safe to navigate to: a path inside this app only.
 * Anything else (another site, `//host`, a backslash trick, a scheme) is
 * dropped for the default, so a link cannot send someone elsewhere after
 * they sign in.
 */
export function safeNextPath(value: string | string[] | undefined | null): Route {
  const raw = Array.isArray(value) ? value[0] : value;
  if (
    typeof raw !== 'string' ||
    raw.length > NEXT_MAX ||
    !raw.startsWith('/') ||
    raw.startsWith('//') ||
    raw.includes('\\') ||
    hasControlCharacter(raw)
  ) {
    return DEFAULT_LANDING;
  }
  return raw as Route;
}

/** A mailed link's token, carried after `#token=` so it never reaches a server log (docs/AUTH.md). */
export function fragmentToken(hash: string): string | null {
  const token = new URLSearchParams(hash.replace(/^#/, '')).get('token');
  return token !== null && token.length >= 16 && token.length <= 256 ? token : null;
}

/**
 * The API route that starts a Google sign-in; it is a page navigation, not a
 * request. An acceptance of the terms never travels in it: the sign-up view
 * keeps its tick in this tab (src/account/legal-tick.ts) for the way back.
 */
export function googleStartUrl(next: Route): string {
  const url = new URL('/auth/google/start', apiOrigin());
  url.searchParams.set('next', next);
  return url.href;
}

/** The sign-in page, coming back to `path` afterwards. */
export function signInHref(path: string): Route {
  return `/signin?next=${encodeURIComponent(safeNextPath(path))}` as Route;
}
