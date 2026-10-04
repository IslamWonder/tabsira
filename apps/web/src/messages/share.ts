/**
 * The words of sharing an insight: the share sheet of the insight screen and
 * the text the share card image carries besides the title and the sources.
 * Wording follows docs/spec/tajriba.md §7: an action is named by what it does and
 * nothing is announced before it has happened.
 *
 * What the API says (the title, the notice of a hadith awaiting its ruling, the
 * engine label, the author) is shown as the API sends it and is not written
 * here. No Quran or hadith text belongs in this file, ever.
 */

export const shareMessages = {
  sharing: {
    title: 'شارك البصيرة',
    /** Said before the first publication: exactly what becomes public. */
    whatBecomesPublic:
      'عند النشر تصير البصيرة صفحةً عامة يراها أي شخص، وقد تظهر في نتائج البحث: عنوانها ولمحتها والآية والحديث وشرح تبصرة وخطوتها الصغيرة. لا تظهر فيها صورتك ولا موقعك ولا محادثتك، ولا اسمك إلا إن اخترت اسمًا عامًّا. تسحبها متى شئت فتزول الصفحة فورًا.',
    publicNow:
      'هذه البصيرة منشورة الآن: يراها أي شخص، وقد تظهر في نتائج البحث. اسحبها متى شئت فتزول الصفحة فورًا.',
    publishAndShare: 'انشر وشارك',
    share: 'شارك الرابط',
    withdraw: 'اسحب النشر',
    working: 'لحظة…',
    linkLabel: 'رابط البصيرة',
    copied: 'نُسخ الرابط.',
    withdrawn: 'سُحبت البصيرة، ولم تعد صفحتها متاحة لأحد.',
    notPublishable:
      'لا يمكن نشر هذه البصيرة: إمّا أن مشهدها حساس، أو أن نصها لا يحمل ما يلزم من القرآن أو السنة من مصدرهما المعتمد.',
    copyFailed: 'تعذّر النسخ. انسخ الرابط المعروض يدويًا.',
  },

  shareCard: {
    /** Under the verse when the hadith is too long to fit whole on the card. */
    hadithOnPage: 'الحديث كاملًا في صفحة البصيرة',
    /** The hadith's reference followed by the ruling, as recorded. */
    hadithWithRuling: (reference: string, ruling: string) => `${reference}، ${ruling}`,
    /** The line before the author's public name. */
    by: 'نشرها',
  },
} as const;
