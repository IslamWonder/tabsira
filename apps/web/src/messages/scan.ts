/**
 * The words of the journey from a photo to an insight: starting a scan, its
 * honest progress, the choice of focus, the one clarifying question, the
 * insight page, the chat, «تمّ» and what follows it. Wording follows
 * docs/spec/tajriba.md §7: one name per action, nothing announced before it
 * has happened, a fault of ours never put on the reader.
 *
 * What the API itself says (the labels of a relation, of the small step, of a
 * prepared example or a simulation, the notice of a hadith awaiting its ruling,
 * the explanation texts) is shown as the API sends it and is not written here.
 * No Quran or hadith text belongs in this file, ever.
 */

export const scanMessages = {
  sending: {
    title: 'صورتك',
    file: (name: string) => `أرسل «${name}» لتحليلها…`,
    link: 'أطلب الصورة من الرابط وأحلّلها…',
    cancel: 'ألغِ',
    retry: 'أعد المحاولة',
    close: 'عد إلى المشهد',
    /** Said before the photo leaves the device (master prompt §19). */
    privacy:
      'تُرسل صورتك إلى مزوّد الذكاء الاصطناعي لتحليلها، وتبقى في خادمنا ساعة واحدة على الأكثر ثم تُمسح، ولا نعرضها عليك ولا نحفظها إن بدا المشهد حساسًا.',
    opening: 'أفتح البصيرة…',
    openFailed: 'تعذّر فتح البصيرة الآن.',
  },

  scan: {
    metaTitle: 'مشهدك',
    loading: 'نفتح مشهدك…',
    retry: 'أعد المحاولة',
    another: 'جرّب مشهدًا آخر',
    photoAlt: 'صورتك التي أرسلتها',
    /** Until the verdict on sensitivity is known, no photo is shown. */
    photoWaiting: 'تظهر صورتك هنا بعد أن نفحصها.',
    sensitive: 'لن نعرض هذه الصورة ولن نحفظها. نعرض لك المعنى وحده.',
    photoGone: 'مضت ساعة فمُسحت الصورة من خادمنا؛ تبقى بصائرك.',
    described: 'ما رأيناه في المشهد',
    pick: 'المس البصيرة التي لفتتك',
    open: 'افتح البصيرة',
    ready: 'بصائر هذا المشهد',
    completedGlimpse: (glimpse: string) => `تمّت · ${glimpse}`,
    noEvidence: {
      title: 'لم أجد صلة موثوقة بهذا المشهد بعد',
      body: 'لا نكمل بنص بعيد لنملأ الفراغ. حدّد ما لفت نظرك لننظر إليه وحده، أو جرّب مشهدًا آخر.',
      awaiting:
        'ثمة حديث مرتبط بهذا المشهد بانتظار التحقق من حكمه في الدرر، ولذلك لم تكتمل البصيرة بعد.',
    },
    failed: {
      title: 'لم تكتمل قراءة المشهد',
    },
    focus: {
      open: 'ما الذي لفت نظرك؟',
      title: 'ما الذي لفت نظرك؟',
      hint: 'اختر شيئًا في الصورة لننظر إليه وحده.',
      photoLabel: 'الأشياء في الصورة',
      listLabel: 'ما وجدناه في الصورة',
      inferred: 'مُرجَّح',
      confirm: 'انظر إلى هذا',
      confirming: 'أنظر…',
      cancel: 'ارجع',
      none: 'لم نتعرف على شيء يمكن اختياره هنا. جرّب مشهدًا آخر.',
      chosen: (label: string) => `اخترت: ${label}`,
    },
    clarify: {
      title: 'سؤال واحد قبل أن نكمل',
      label: 'جوابك',
      hint: 'جملة قصيرة تكفي.',
      submit: 'أجب وأكمل',
      submitting: 'أرسل جوابك…',
      empty: 'اكتب جوابك أولًا.',
    },
    errors: {
      IMAGE_EMPTY: 'الملف فارغ. اختر صورة أخرى.',
      IMAGE_TOO_LARGE: 'الصورة أكبر مما نقبل. اختر صورة أصغر.',
      IMAGE_TOO_SMALL: 'الصورة أصغر من أن نفهم المشهد منها. اختر صورة أكبر.',
      IMAGE_UNSUPPORTED: 'هذه الصيغة غير مدعومة. اختر صورة بصيغة JPEG أو PNG أو WebP أو HEIC.',
      IMAGE_INVALID: 'تعذّرت قراءة هذا الملف كصورة. جرّب صورة أخرى.',
      IMAGE_URL_REFUSED:
        'لا نستطيع جلب صورة من هذا العنوان. استعمل رابطًا عامًا مباشرًا لصورة، يبدأ بـ https.',
      IMAGE_FETCH_FAILED:
        'تعذّر جلب الصورة من الرابط. تأكد أنه رابط مباشر لصورة، أو نزّلها واختر الملف.',
      QUEUE_UNAVAILABLE: 'تعذّر بدء التحليل الآن من جهتنا لا من جهتك. أعد المحاولة بعد قليل.',
      SCAN_BUSY: 'ما زلنا نحلّل هذا المشهد. انتظر حتى ينتهي.',
      CONFLICT: 'لا يقبل المشهد هذا الطلب في حالته الآن. حدّث الصفحة.',
      NOT_FOUND: 'لم نجد هذا المشهد عندك. ربما هو من جهاز أو حساب آخر.',
      ASSET_MISSING:
        'مُسحت الصورة من خادمنا بعد ساعة، ولا يمكننا النظر فيها مرة أخرى. صوّر المشهد من جديد.',
      MODEL_UNAVAILABLE: 'تعذّر الوصول إلى خدمة التحليل الآن. أعد المحاولة بعد قليل.',
      VISION_FAILED: 'لم نستطع قراءة هذه الصورة. جرّب صورة أوضح أو بإضاءة أفضل.',
      SOURCE_UNAVAILABLE:
        'تعذّر الوصول إلى مصادر القرآن والسنة حاليًا. لا نعوّض ذلك بنص مولّد؛ أعد المحاولة بعد قليل.',
      SCAN_TIMEOUT: 'استغرق التحليل أطول مما ينبغي ولم يكتمل. أعد المحاولة بصورة أخرى.',
      CHAT_LIMIT_REACHED: 'اكتمل النقاش حول هذه البصيرة',
      CHAT_IN_PROGRESS: 'ما زلنا نجيب عن سؤالك السابق. انتظر قليلًا ثم أعد المحاولة.',
      CHAT_ANSWER_REJECTED: 'تعذّر تقديم جواب موثوق عن هذا السؤال. أعد صياغته بكلمات أخرى.',
      FEATURE_DISABLED: 'هذه الميزة غير متاحة الآن.',
      SAVE_FAILED: 'لم تُحفظ البصيرة. أعد المحاولة؛ لن تُحفظ مرتين.',
    },
  },

  /** The public page of a published insight (master prompt v2 §18). */
  publicInsight: {
    /** The breadcrumb and the fallback name of the page. */
    name: 'بصيرة منشورة',
    byAuthor: (name: string) => `نشرها ${name}`,
    publishedOn: 'نُشرت في',
    tryIt: 'جرّب تبصرة بمشهدك',
    tryItHint: 'صوّر مشهدًا من حولك، وانظر ما تقوله الآية والحديث عنه.',
    /** Before the glimpse in search results: what the page is. */
    descriptionPrefix: 'بصيرة من تبصرة:',
    /** Between the clues of one list. */
    listSeparator: '، ',
  },
  /** The share sheet of the owner's insight: publish, the link, the card (master prompt v2 §18). */
  share: {
    open: 'شارك البصيرة',
    title: 'مشاركة البصيرة',
    description: 'رابط يقرؤه الجميع، وبطاقة تُرسل في أي تطبيق.',
    whatShows:
      'ما يظهر للجميع في صفحة عامة وبطاقة صورة، وقد تفهرسها محركات البحث: عنوان البصيرة ولمحتها، والآية والحديث كما هما في المصدر، وشرح تبصرة، و«لماذا ظهر هذا؟» (ما وصفه النموذج في المشهد، والمعنى، وحدود الصلة)، والخطوة الصغيرة، وعلامة المثال المُعدّ إن كانت، وتاريخ النشر، واسمك العام إن اختَرته. البطاقة تحمل العنوان ومرجعَي الآية والحديث لا نصّيهما. لا تظهر الصورة نفسها ولا حوارك ولا ملفك ولا سجل تعلّمك. تستطيع إلغاء النشر في أي وقت؛ ما نُسخ أو حُمّل قبل ذلك يبقى عند من أخذه.',
    publish: 'انشر البصيرة',
    publishing: 'ننشر…',
    published: 'البصيرة منشورة',
    withdraw: 'إلغاء النشر',
    withdrawing: 'نلغي النشر…',
    link: 'رابط البصيرة',
    copy: 'نسخ الرابط',
    copied: 'نُسخ الرابط',
    copyFailed: 'لم يُنسخ الرابط. انسخه من الحقل.',
    system: 'مشاركة',
    download: 'تنزيل البطاقة',
    cardAlt: 'بطاقة البصيرة للمشاركة',
    shareText: (title: string) => `بصيرة من تبصرة: ${title}`,
    failures: {
      notPublishable:
        'لا يمكن نشر هذه البصيرة: لا يُنشر إلا ما تحقّقت نصوصه، ولا تُنشر المحاكاة، ولا بصيرة كُتبت لك بصفة شخصية، ولا تُتاح صفحة عامة لمن أعلن أنه دون 13 سنة.',
      verify: 'وثّق بريدك أولًا من صفحة «ملفي» ليمكنك النشر.',
      signIn: 'سجّل الدخول لنشر بصيرتك.',
      forbidden: 'النشر غير متاح لهذا الحساب.',
      other: 'لم يتم ذلك. حاول بعد قليل.',
    },
    card: {
      fullTextOnPage: 'النص كاملًا في الصفحة',
      brand: 'تبصرة',
    },
  },
  insightPage: {
    metaTitle: 'بصيرتك',
    loading: 'نفتح بصيرتك…',
    retry: 'أعد المحاولة',
    photoAlt: 'صورة المشهد',
    photoSensitive: 'لا نعرض صورة هذا المشهد ولا نحفظها.',
    photoGone: 'مُسحت الصورة من خادمنا بعد ساعة، وبقيت البصيرة.',
    photoNone: 'الصورة غير معروضة الآن.',
    verseReference: (surah: string, ayah: number) => `${surah}، الآية ${ayah}`,
    hadithReference: (book: string, number: string) => `${book}، رقم ${number}`,
    rulingSource: (scholar: string, book: string, page: string) => `${scholar}، ${book}، ${page}`,
    awaitingTitle: 'الحديث بانتظار الحكم',
    explanation: 'شرح تبصرة',
    simulation: 'محاكاة',
    why: {
      title: 'لماذا ظهر هذا؟',
      clues: 'ما ظهر في المشهد',
      concept: 'المعنى',
      sources: 'المصادر',
      sourceQuran: 'القرآن',
      sourceSunnah: 'السنة',
      sourceLine: (relation: string, matched: string) =>
        matched === '' ? relation : `${relation}، وجه الصلة: ${matched}`,
      limits: 'حدود هذه الصلة',
      personalisation: 'التخصيص',
      personalised: 'اختيارٌ بُني على ما صرّحت به في ملفك:',
      notPersonalised: 'لم يُبنَ هذا الاختيار على ملفك.',
    },
    step: {
      confirm: 'نفّذته',
    },
    chat: {
      open: 'ناقش البصيرة',
      title: 'ناقش البصيرة',
      used: (used: number, limit: number) => `استُعمل ${used} من ${limit}`,
      remaining: 'أسئلتك على هذه البصيرة',
      label: 'سؤالك',
      hint: 'سؤال واحد في كل مرة، حتى 500 حرف.',
      send: 'اسأل',
      sending: 'أجيب…',
      limit: 'اكتمل النقاش حول هذه البصيرة',
      disabled: 'النقاش غير متاح الآن.',
      asked: 'سؤالك',
      answered: 'الجواب',
      empty: 'اكتب سؤالك أولًا.',
      emptyState: 'لم تسأل شيئًا بعد.',
    },
    done: {
      saving: 'أحفظ بصيرتك…',
      failed: 'لم تُحفظ البصيرة. أعد المحاولة؛ لن تُحفظ مرتين.',
      alreadyTitle: 'اكتملت هذه البصيرة',
      alreadyBody: 'تجد أثرها في عالمك.',
    },
  },

  completion: {
    title: 'اكتملت بصيرتك',
    placeNew: (name: string) => `أضيفت «${name}» إلى عالمك`,
    placeSeen: (name: string) => `«${name}» في عالمك من قبل`,
    treasure: 'ثمّة كنز مخبوء ينتظرك حين تعود.',
    quest: 'مهمة اليوم',
    questDone: 'أتممت مهمة اليوم',
    questStepDone: 'تمّت',
    badges: 'علامة تمرين جديدة',
    openWorld: 'افتح عالمي',
    newScan: 'صوّر مشهدًا آخر',
    progressFailed: 'تعذّر عرض مهمة اليوم وعلاماتك الآن، وبصيرتك محفوظة.',
  },
} as const;
