import { siteLanguage } from '@/messages';

/** A calendar day in the site's language, with Western digits (docs/SEO.md §4). */
export function formatDay(iso: string): string {
  return new Intl.DateTimeFormat(siteLanguage.intl, { dateStyle: 'long' }).format(new Date(iso));
}

/** A date and time in the site's language, with Western digits (docs/SEO.md §4). */
export function formatWhen(iso: string): string {
  return new Intl.DateTimeFormat(siteLanguage.intl, {
    dateStyle: 'long',
    timeStyle: 'short',
  }).format(new Date(iso));
}
