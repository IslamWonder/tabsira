import { siteLanguage } from '@/messages';

/** The time zone dates are shown in to people: the owners' (production itself runs in UTC). */
export const DISPLAY_TIME_ZONE = 'Africa/Tunis';

/**
 * A calendar day in the site's language, with Western digits (docs/SEO.md §4).
 * Pass `timeZone` where the server renders the day, so the server's own zone never decides it.
 */
export function formatDay(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat(siteLanguage.intl, { dateStyle: 'long', timeZone }).format(
    new Date(iso)
  );
}

/** A date and time in the site's language, with Western digits (docs/SEO.md §4). */
export function formatWhen(iso: string): string {
  return new Intl.DateTimeFormat(siteLanguage.intl, {
    dateStyle: 'long',
    timeStyle: 'short',
  }).format(new Date(iso));
}
