import type { LandingFeatures } from '@/components/landing/landing-model';
import type { components } from '@/lib/api/schema';
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

/** A feature switch: the names of the API's `FeatureFlag`, from its generated types. */
export type FeatureFlag = components['schemas']['FeatureFlag'];

// The rule of decision 63, the same as apps/api/src/features.py: every feature is on unless
// DISABLED_FEATURES names it, except these, which are on only when ENABLED_FEATURES names them.
const OFF_BY_DEFAULT: ReadonlySet<FeatureFlag> = new Set<FeatureFlag>([
  'social_comments',
  'camera_anchor',
]);

// child -> parent: a child counts as off whenever its parent is off.
const PARENT: Readonly<Partial<Record<FeatureFlag, FeatureFlag>>> = {
  social_comments: 'social',
  atlas_sponsorship: 'atlas',
  camera_anchor: 'camera_discovery',
  dev_inspector: 'admin',
};

// The API refuses a name it does not know at start, so the web ignores one rather than crash.
function names(raw: string | undefined): ReadonlySet<string> {
  return new Set(
    (raw ?? '')
      .split(',')
      .map((name) => name.trim())
      .filter((name) => name !== '')
  );
}

/**
 * Whether a feature is on. DISABLED_FEATURES and ENABLED_FEATURES are read at request time from
 * the same environment file as the API (deploy/ecosystem.config.cjs); ENABLED_FEATURES wins, and
 * a child is off while its parent is. Server code only: nothing is baked into the bundle.
 */
export function featureEnabled(flag: FeatureFlag, env: Env = process.env): boolean {
  const own =
    names(env.ENABLED_FEATURES).has(flag) ||
    (!OFF_BY_DEFAULT.has(flag) && !names(env.DISABLED_FEATURES).has(flag));
  const parent = PARENT[flag];
  return own && (parent === undefined || featureEnabled(parent, env));
}

/**
 * What the landing page may announce: the public subset of the features, read here at request
 * time and handed to the page as plain values. Nothing administrative is in it, and the
 * camera anchor, off by default, is not a thing the page ever offers.
 */
export function landingFeatures(env: Env = process.env): LandingFeatures {
  return {
    chat: featureEnabled('chat', env),
    world: featureEnabled('world', env),
    treasure: featureEnabled('treasure', env),
    social: featureEnabled('social', env),
    atlas: featureEnabled('atlas', env),
    cameraDiscovery: featureEnabled('camera_discovery', env),
    photoStorage: featureEnabled('photo_storage', env),
    canonicalVerify: featureEnabled('canonical_verify', env),
  };
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
