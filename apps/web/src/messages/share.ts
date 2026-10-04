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
    /** A plain download of the card image (v2 §18), beside sharing and copying the link. */
    download: 'نزّل البطاقة',
    withdraw: 'اسحب النشر',
    working: 'لحظة…',
    linkLabel: 'رابط البصيرة',
    copied: 'نُسخ الرابط.',
    withdrawn: 'سُحبت البصيرة، ولم تعد صفحتها متاحة لأحد.',
    notPublishable:
      'لا يمكن نشر هذه البصيرة. لا تُنشر إلا البصائر التي جاءت من تحليل حقيقي لصورتك ولم يُبنَ شيء منها على ما في ملفك، وكان في كل منها ما يُعرض من القرآن أو السنة من مصدرهما المعتمد، وليس مشهدها حساسًا، ولم يظهر في نصوص المنصة ما يشبه آيةً أو حديثًا.',
    copyFailed: 'تعذّر النسخ. انسخ الرابط المعروض يدويًا.',
    /** The two other ways to publish (extension §2.3–2.4), each its own choice with its own preview. */
    moreWays: 'طرق نشر أخرى',
    publishMap: 'انشر على الخريطة',
    publishCommunity: 'انشر في تواصل',
    publishSeparate:
      'كلٌّ منهما نشر مستقل تعاينه قبل أن يتم. النشر على الخريطة يجعل البصيرة قابلة للاكتشاف على الأطلس وبالكاميرا في موقعها التقريبي، ولا يفعّل النشر في تواصل.',
    /** The account said in its profile that it is under 13: nothing of its own is published. */
    notForUnder13:
      'لا يُتاح النشر العام لمن أعلن في ملفه أنه دون 13 سنة. البصيرة تبقى في عالمك، ويمكنك تعديل نطاق العمر في ملفك إن كان خطأ.',
  },

  shareCard: {
    /** Under the verse when the hadith is too long to fit whole on the card. */
    hadithOnPage: 'الحديث كاملًا في صفحة البصيرة',
    /** The hadith's reference, then the source's own words on its ruling and who gave it, each on its own line. */
    hadithWithRuling: (reference: string, ruling: string, source: string) =>
      `${reference}\n${ruling}\n${source}`,
    /** The author's public name and handle; the handle is isolated so it keeps its own direction in the right-to-left line. */
    author: (name: string, handle: string) => `نشرها ${name} \u2066@${handle}\u2069`,
  },
} as const;
