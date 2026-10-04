import { DEVELOPMENT_API_URL, DEVELOPMENT_SITE_URL } from '@/config/public-env';

// next.config.ts validates both addresses and inlines them at build time; the
// .test fallbacks only ever apply to tests and to `next dev` without a .env.

/** Origin of the web app, the base of canonical and share URLs. */
export function siteOrigin(value: string | undefined = process.env.NEXT_PUBLIC_SITE_URL): URL {
  return new URL(value || DEVELOPMENT_SITE_URL);
}

/** Origin of the API the browser calls. */
export function apiOrigin(value: string | undefined = process.env.NEXT_PUBLIC_API_URL): string {
  return value || DEVELOPMENT_API_URL;
}
