import { ar, type Messages } from './ar';

/*
 * The languages of the interface (owner decision 36). Arabic only today; a
 * second language is one more entry here and one more catalogue beside ar.ts,
 * with no URL moving: there is no locale in any path and no switcher.
 */
export const LANGUAGES = {
  ar: {
    /** The `lang` attribute, and the base of every Intl format. */
    tag: 'ar',
    dir: 'rtl',
    /** Open Graph's locale form. */
    ogLocale: 'ar_AR',
    /** Dates and numbers: Arabic words with Western digits (docs/SEO.md §4). */
    intl: 'ar-u-nu-latn',
  },
} as const;

export type Language = keyof typeof LANGUAGES;

/** The one language the site is served in; `lang`, `dir` and the messages follow it. */
export const SITE_LANGUAGE: Language = 'ar';

const CATALOGUES: Record<Language, Messages> = { ar };

export function getMessages(language: Language = SITE_LANGUAGE): Messages {
  return CATALOGUES[language];
}

/** Every user-visible string of the interface, in the site's language. */
export const messages: Messages = getMessages();

/** The settings of the site's language. */
export const siteLanguage = LANGUAGES[SITE_LANGUAGE];

export type { Messages };
