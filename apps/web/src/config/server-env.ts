import { apiOrigin, siteOrigin } from '@/lib/site';

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

// A Clarity project id: lower-case letters and digits, ten of them in practice.
const CLARITY_ID = /^[a-z0-9]{6,16}$/;

/** CLARITY_PROJECT_ID, or null when it is empty or malformed: then no heatmaps (owner decision 32). */
export function clarityProjectId(env: Readonly<Record<string, string | undefined>> = process.env) {
  const value = env.CLARITY_PROJECT_ID?.trim() ?? '';
  return CLARITY_ID.test(value) ? value : null;
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

/**
 * The public address of the site, read from SITE_URL when a request comes in
 * (never baked at build time), for what is written outside a page: the
 * sitemap. A missing or malformed value falls back to the build's own address.
 */
export function serverSiteOrigin(env: Env = process.env): URL {
  try {
    return new URL(env.SITE_URL?.trim() ?? '');
  } catch {
    return siteOrigin();
  }
}

/** How long the sitemap waits for the API: a page of 10 000 entries is more than a consent check. */
export const SITEMAP_TIMEOUT_MS = 10_000;

// The spellings pydantic accepts for a boolean setting, so the web and the API read one value alike.
const TRUE_WORDS = new Set(['1', 'true', 't', 'yes', 'y', 'on']);

/**
 * A FEATURE_* flag the web server reads at request time, from the same
 * environment file as the API (deploy/ecosystem.config.cjs): on unless the
 * value says otherwise, as the API's own defaults are. Server code only; no
 * flag is baked into the bundle.
 */
export function featureFlag(name: string, env: Env = process.env): boolean {
  const value = env[`FEATURE_${name}`]?.trim().toLowerCase() ?? '';
  return value === '' ? true : TRUE_WORDS.has(value);
}

/** The camera discovery, levels A and B (decision 9); off in production until proven on phones. */
export function featureCameraDiscovery(env: Env = process.env): boolean {
  return featureFlag('CAMERA_DISCOVERY', env);
}
