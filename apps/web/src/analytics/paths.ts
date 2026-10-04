/**
 * Where no analytics tool runs (owner decision 28): the admin and developer
 * areas, sign-in and sign-up, the mailed-link pages, and everything of the
 * account (the profile page). A page is excluded by its path only, never by who looks.
 */
const EXCLUDED_PREFIXES = [
  '/admin',
  '/dev',
  '/signin',
  '/signup',
  '/login',
  '/forgot-password',
  '/reset-password',
  '/verify-email',
  '/me',
] as const;

export function isExcludedPath(pathname: string): boolean {
  return EXCLUDED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

/** Public insights carry the insight's text in the page; no heatmap tool records them (owner decision 32). */
const HEATMAP_ONLY_EXCLUDED = ['/insights'] as const;

export function isHeatmapExcludedPath(pathname: string): boolean {
  return (
    isExcludedPath(pathname) ||
    HEATMAP_ONLY_EXCLUDED.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
  );
}

/** The route template that stands for the page title of a public insight; the title is the insight's text. */
export const PUBLIC_INSIGHT_TITLE = '/insights/[id]';

/** The title analytics may read for a path: a fixed one where the document title is an insight's text, else none set. */
export function analyticsPageTitle(pathname: string): string | undefined {
  return pathname === '/insights' || pathname.startsWith('/insights/')
    ? PUBLIC_INSIGHT_TITLE
    : undefined;
}
