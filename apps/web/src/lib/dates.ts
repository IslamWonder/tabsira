import { siteLanguage } from '@/messages';

/** A date and time in the site's language, with Western digits (docs/SEO.md §4). */
export function formatWhen(iso: string): string {
  return new Intl.DateTimeFormat(siteLanguage.intl, {
    dateStyle: 'long',
    timeStyle: 'short',
  }).format(new Date(iso));
}
