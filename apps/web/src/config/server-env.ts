import { apiOrigin } from '@/lib/site';

/**
 * Configuration the web server reads at request time, never at build time
 * (owner decision 28: a build must not bake in the analytics id). Server
 * code only: nothing here is NEXT_PUBLIC_, so nothing reaches the bundle.
 */

// A GA4 measurement id: "G-" and letters or digits. Anything else is treated as unset.
const MEASUREMENT_ID = /^G-[A-Z0-9]{4,20}$/;

/** GA_MEASUREMENT_ID, or null when it is empty or malformed: then no analytics code at all. */
export function gaMeasurementId(env: Readonly<Record<string, string | undefined>> = process.env) {
  const value = env.GA_MEASUREMENT_ID?.trim() ?? '';
  return MEASUREMENT_ID.test(value) ? value : null;
}

type Env = Readonly<Record<string, string | undefined>>;

/** The API of `make dev` (scripts/dev-api.sh), on loopback: the server need not trust mkcert. */
export const DEVELOPMENT_INTERNAL_API_URL = 'http://127.0.0.1:8000';

/**
 * Where the web server itself reaches the API (the consent check of the first
 * paint, the cookie form without JavaScript): API_INTERNAL_URL, such as the
 * API's loopback address on the same host; else, outside production, the
 * development API on loopback; else the public API address.
 */
export function serverApiOrigin(env: Env = process.env): string {
  const value = env.API_INTERNAL_URL?.trim() ?? '';
  if (value !== '') {
    return new URL(value).origin;
  }
  return env.NODE_ENV === 'production' ? apiOrigin() : DEVELOPMENT_INTERNAL_API_URL;
}

/** How long the server waits for the API before rendering without it (AGENTS.md lessons). */
export const SERVER_API_TIMEOUT_MS = 1500;
