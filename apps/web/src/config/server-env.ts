import type { LandingFeatures } from '@/components/landing/landing-model';
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

/**
 * What the landing page may announce: the public subset of the flags, read here at request
 * time and handed to the page as plain values. Nothing administrative is in it, and the
 * camera anchor, off, is not a thing the page ever offers.
 */
export function landingFeatures(env: Env = process.env): LandingFeatures {
  return {
    chat: featureFlag('CHAT', env),
    world: featureFlag('WORLD', env),
    treasure: featureFlag('TREASURE', env),
    social: featureFlag('SOCIAL', env),
    atlas: featureFlag('ATLAS', env),
    cameraDiscovery: featureFlag('CAMERA_DISCOVERY', env),
    photoStorage: featureFlag('PHOTO_STORAGE', env),
    canonicalVerify: featureFlag('CANONICAL_VERIFY', env),
  };
}

/** The camera discovery, levels A and B (decision 9); off in production until proven on phones. */
export function featureCameraDiscovery(env: Env = process.env): boolean {
  return featureFlag('CAMERA_DISCOVERY', env);
}

/** The admin area of `make dev`; production names its own in ADMIN_URL (docs/ADMIN.md). */
export const DEVELOPMENT_ADMIN_URL = 'http://admin.tabsira.test';

// A public id as the API writes it: a positive decimal that fits 64 bits.
const SCAN_ID = /^[1-9][0-9]{0,18}$/;

/**
 * Where the developer panel of a scan lives (v2 §23): the scan inspector of the
 * admin area, on the admin host, behind an admin session. The web app's own
 * `/dev/inspect/{scanId}` only hands over to it, because an admin session exists
 * on that host alone. Null when the id is not one.
 */
export function adminInspectorUrl(scanId: string, env: Env = process.env): string | null {
  if (!SCAN_ID.test(scanId)) {
    return null;
  }
  const base = env.ADMIN_URL?.trim() || DEVELOPMENT_ADMIN_URL;
  return new URL(`/admin/inspect/${scanId}`, base).toString();
}

/** The world atlas: while it is off, its pages do not exist (decision 1), as the API's routes do not. */
export function featureAtlas(env: Env = process.env): boolean {
  return featureFlag('ATLAS', env);
}

/** The social network: while it is off, its pages do not exist (decision 1), as the API's routes do not. */
export function featureSocial(env: Env = process.env): boolean {
  return featureFlag('SOCIAL', env);
}

// A Turnstile site key: letters, digits, "_" and "-" (Cloudflare's own begin with "0x4" or "1x0").
const TURNSTILE_KEY = /^[0-9A-Za-z_-]{8,64}$/;

/**
 * TURNSTILE_SITE_KEY, or an empty string when it is unset or malformed: then
 * Turnstile is off, nothing is rendered or loaded and no header is sent
 * (decision 56). Public by nature, but read here at request time, never baked
 * into the build.
 */
export function turnstileSiteKey(env: Env = process.env): string {
  const value = env.TURNSTILE_SITE_KEY?.trim() ?? '';
  return TURNSTILE_KEY.test(value) ? value : '';
}
