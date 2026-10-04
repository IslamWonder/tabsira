/**
 * The text the share card image carries besides the title and the sources.
 * Wording follows docs/spec/tajriba.md §7: an action is named by what it does and
 * nothing is announced before it has happened.
 *
 * What the API says (the title, the notice of a hadith awaiting its ruling, the
 * engine label, the author) is shown as the API sends it and is not written
 * here. No Quran or hadith text belongs in this file, ever.
 */

export const shareMessages = {
  shareCard: {
    /** Under the verse when the hadith is too long to fit whole on the card. */
    hadithOnPage: 'الحديث كاملًا في صفحة البصيرة',
    /** The hadith's reference followed by the ruling, as recorded. */
    hadithWithRuling: (reference: string, ruling: string) => `${reference}، ${ruling}`,
    /** The line before the author's public name. */
    by: 'نشرها',
    alt: (title: string) => `بطاقة بصيرة: ${title}`,
  },
} as const;
