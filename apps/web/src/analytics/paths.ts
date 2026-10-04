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
