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
      'عند النشر تصير البصيرة صفحةً عامة وصورةَ مشاركة يراهما أي شخص، وقد تظهران في نتائج البحث: عنوانها ولمحتها والآية والحديث وشرح تبصرة وخطوتها الصغيرة وتاريخ النشر. لا تظهر فيها صورتك ولا موقعك ولا محادثتك، ولا اسمك العام ومعرّفك إلا إن اخترتهما. تسحبها متى شئت فتزول الصفحة والصورة فورًا، إلا ما نسخه غيرك قبل ذلك.',
    publicNow:
      'هذه البصيرة منشورة الآن: صفحتها وصورتها يراهما أي شخص، وقد تظهران في نتائج البحث. اسحبها متى شئت فتزول الصفحة والصورة فورًا، إلا ما نسخه غيرك قبل ذلك.',
    publishAndShare: 'انشر وشارك',
    share: 'شارك الرابط',
    withdraw: 'اسحب النشر',
    working: 'لحظة…',
    linkLabel: 'رابط البصيرة',
    copied: 'نُسخ الرابط.',
    withdrawn: 'سُحبت البصيرة، ولم تعد صفحتها متاحة لأحد.',
    notPublishable:
      'لا يمكن نشر هذه البصيرة. لا تُنشر إلا البصائر التي جاءت من تحليل حقيقي لصورتك ولم يُبنَ شيء منها على ما في ملفك، وكان في كل منها ما يُعرض من القرآن أو السنة من مصدرهما المعتمد، وليس مشهدها حساسًا.',
    copyFailed: 'تعذّر النسخ. انسخ الرابط المعروض يدويًا.',
  },

  shareCard: {
    /** Under the verse when the hadith is too long to fit whole on the card. */
    hadithOnPage: 'الحديث كاملًا في صفحة البصيرة',
    /** The hadith's reference followed by the ruling, as recorded. */
    hadithWithRuling: (reference: string, ruling: string) => `${reference}، ${ruling}`,
    /** The author's public name and handle; the handle is isolated so it keeps its own direction in the right-to-left line. */
    author: (name: string, handle: string) => `نشرها ${name} \u2066@${handle}\u2069`,
  },
} as const;
