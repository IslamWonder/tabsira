import { scanMessages } from './scan';
import { shareMessages } from './share';

/**
 * Every user-visible string of the web app (AGENTS.md: Arabic copy lives here,
 * never inline). Wording follows docs/spec/tajriba.md §7: an action is named by
 * what it does, one name per action across every screen, and nothing is
 * announced before it has happened.
 *
 * No Quran or hadith text belongs here, ever: scripture comes from the API by
 * id and is displayed byte for byte. The gallery's placeholders say so openly.
 */

export const ar = {
  meta: {
    siteName: 'تبصرة',
    title: 'تبصرة · انظر إلى العالم بعين الوحي',
    titleTemplate: '%s · تبصرة',
    description:
      'صوّر مشهدًا من حولك، فتريك تبصرة بصيرةً فيه تسندها آية من القرآن وحديث من السنة، بالعربية.',
    shortDescription: 'بصيرة من مشهدك، تسندها آية وحديث.',
  },

  /** Text for search engines, share cards and agents (docs/SEO.md): never shown in the interface. */
  seo: {
    /** The first crumb of every breadcrumb trail. */
    home: 'الرئيسية',
    /** The share line of the home page: the reason to tap, distinct from its headline. */
    homeShare: 'صوّر مشهدًا من حولك، وانظر ما تقوله الآية والحديث عنه.',
    organizationDescription: 'تبصرة تطبيق عربي يحوّل صورة مشهد إلى بصيرة تسندها آية وحديث.',
    llms: {
      summaryHeading: 'عن الموقع',
      pagesHeading: 'الصفحات العامة',
      rulesHeading: 'ما يجب أن يعرفه القارئ الآلي',
      rules: [
        'اللغة العربية وحدها، من اليمين إلى اليسار.',
        'نصوص القرآن والحديث تُعرض كما هي من مصدرها المحقَّق، ولا يولّدها أي نموذج.',
        'صفحات الحساب والإدارة ليست للفهرسة.',
      ],
    },
  },

  brand: {
    /** The logo's accessible name. */
    name: 'تبصرة',
    tagline: 'انظر إلى العالم بعين الوحي',
    promise: 'لا نريك آية في الشيء فحسب؛ نعلّمك كيف تنظر إليه.',
  },

  a11y: {
    skipToContent: 'انتقل إلى المحتوى',
    opensInNewTab: '(يفتح في نافذة جديدة)',
  },

  nav: {
    label: 'التنقل الرئيسي',
    world: 'عالمي',
    community: 'تواصل',
    capture: 'التقط',
    atlas: 'الأطلس',
    me: 'ملفي',
    captureScene: 'صوّر مشهدًا',
    signIn: 'دخول',
  },

  comingSoon: {
    badge: 'قريبًا',
  },

  pages: {
    home: {
      stageLabel: 'المشهد',
      title: 'المشهد الأول قيد الإعداد',
      description:
        'هنا سيظهر مشهد موثّق فيه بصيرتان؛ تلمس إحداهما فترى الآية والحديث اللذين يسندانها، ثم خطوة صغيرة تعيشها.',
      next: 'وبعده تصوّر مشهدك أنت.',
    },
    world: {
      mapLabel: 'خريطة عالمي',
      title: 'عالمي',
      description: 'خريطتك الخاصة: يتّضح فيها مكانٌ كلما حفظت بصيرة، وتصل بين مكانين صلةٌ مسجّلة.',
    },
    community: {
      title: 'تبصرة تواصل',
      description: 'بصائر موثّقة ينشرها أصحابها؛ تتابعهم، وتحفظ ما ينفعك، وتعلّق بأدب.',
    },
    atlas: {
      mapLabel: 'خريطة الأطلس',
      title: 'أطلس بصائر العالم',
      description: 'بصائر الناس على خريطة العالم في أماكنها التقريبية، تكتشف منها ما حولك.',
    },
    me: {
      title: 'ملفي',
      description: 'حسابك وتفضيلاتك وما حفظته، تتحكم فيها كلها وتحذفها متى شئت.',
      sectionsLabel: 'أقسام ملفي',
      sections: {
        account: 'حسابك',
        about: 'عنك',
        identity: 'هويتك العامة',
        settings: 'الإعدادات',
        practice: 'تمرينك',
        data: 'بياناتك',
        cookies: 'ملفات تعريف الارتباط',
      },
      loading: 'نحمّل حسابك…',
      unavailable: 'تعذّر الوصول إلى حسابك الآن. إعدادات هذا الجهاز تعمل كما هي.',
      retry: 'أعد المحاولة',
      guest: {
        title: 'لم تدخل بعد',
        body: 'ادخل لتحفظ مسارك وبصائرك وتجدها على أي جهاز. الحساب اختياري، والتجربة كلها متاحة دونه.',
        signIn: 'ادخل',
        signUp: 'أنشئ حسابًا',
        accountSettings: 'التخصيص والذاكرة وحفظ الصور خيارات لحسابك، تجدها هنا بعد الدخول.',
      },
      account: {
        email: 'البريد',
        verified: 'مؤكَّد',
        unverified: 'لم يُؤكَّد بعد',
        unverifiedHint: 'أكّد بريدك قبل أن تنشر شيئًا للناس.',
        resend: 'أرسل رابط التأكيد مرة أخرى',
        resending: 'أرسل…',
        resent: 'إن لم يكن بريدك مؤكَّدًا، فسيصله رابط جديد خلال دقائق.',
        withGoogle: 'تدخل بحساب Google',
      },
      data: {
        exportHint: 'كل ما يحفظه حسابك، في ملف JSON واحد.',
        export: 'نزّل بياناتي',
        exporting: 'أحضّر الملف…',
        exported: 'نُزّل الملف.',
        history: 'سجل الموافقات',
        historyLoading: 'نحمّل السجل…',
        historyEmpty: 'لا موافقات مسجّلة بعد.',
        granted: 'وافقت',
        withdrawn: 'سحبت الموافقة',
        kinds: {
          terms: 'شروط الاستعمال',
          privacy: 'سياسة الخصوصية',
          photo_storage: 'حفظ صوري',
          personalization: 'التخصيص',
          memory: 'الذاكرة',
        },
        textVersion: (version: string) => `نسخة النص ${version}`,
      },
      delete: {
        title: 'حذف الحساب',
        body: 'يُحذف حسابك وملفك وموافقاتك وجلساتك نهائيًا.',
        action: 'احذف حسابي',
        confirmTitle: 'هل تحذف حسابك نهائيًا؟',
        confirmBody:
          'لا يمكن التراجع بعد الحذف، ولن نستطيع استعادة شيء. إن أردت نسخة من بياناتك فنزّلها أولًا.',
        confirm: 'نعم، احذف حسابي نهائيًا',
        cancel: 'تراجع',
        deleting: 'أحذف…',
        deleted: 'حُذف حسابك وكل ما يخصّه.',
      },
      cookies: {
        body: 'اختر ما تسمح به من ملفات القياس، وغيّره متى شئت.',
      },
    },
    notFound: {
      title: 'لم نجد هذه الصفحة',
      description: 'ربما تغيّر الرابط أو أزيلت الصفحة.',
      action: 'عد إلى البداية',
    },
    error: {
      title: 'تعذّر عرض هذه الصفحة',
      description: 'حدث خطأ من جهتنا، لا من جهتك. أعد المحاولة، وإن تكرر فعد بعد قليل.',
      retry: 'أعد المحاولة',
      home: 'عد إلى البداية',
    },
    offline: {
      title: 'أنت غير متصل الآن',
      description:
        'تحتاج تبصرة إلى الاتصال لتفهم المشهد وتجلب الأدلة من مصادرها. تحقق من اتصالك ثم أعد المحاولة.',
      retry: 'أعد المحاولة',
    },
  },

  theme: {
    legend: 'المظهر',
    system: 'تلقائي',
    light: 'فاتح',
    dark: 'داكن',
    hint: '«تلقائي» يتبع إعداد جهازك. يُحفظ اختيارك على هذا الجهاز وحده.',
    toggle: (current: string) => `المظهر: ${current}`,
  },

  preferences: {
    motion: {
      label: 'الحركة الزخرفية',
      hint: 'نقاط الضوء في الخلفية واحتفال «تمّ». تتوقف دائمًا إن طلب جهازك تقليل الحركة.',
    },
    sound: {
      label: 'المؤثر الصوتي',
      hint: 'صوت قصير يُسمع عند فتح البصيرة. يُحفظ اختيارك على هذا الجهاز وحده.',
    },
  },

  sound: {
    toggle: 'المؤثر الصوتي',
    on: 'مفعّل',
    off: 'مُوقَف',
    state: (current: string) => `المؤثر الصوتي: ${current}`,
  },

  sheet: {
    close: 'أغلق',
  },

  scene: {
    prepared: 'مثال موثّق مُعدّ',
    hint: 'المس البصيرة التي لفتتك',
    captureOwn: 'أو صوّر مشهدك أنت',
    listHeading: 'البصائر في الصورة',
    glimpseAndPosition: (glimpse: string, position: string) => `${glimpse}، ${position}`,
    /**
     * The prepared rain scene (tajriba §6): the photo and the two insights' names
     * and glimpses. Their verses, hadiths and explanations come from the API
     * with the curated scene; nothing of them is written here.
     */
    example: {
      alt: 'نبتة زيتون صغيرة تتلقى قطرات المطر',
      insights: [
        { id: 'drop', title: 'الحياة في قطرة', glimpse: 'كيف تُحيا الأرض بعد موتها' },
        { id: 'planting', title: 'الغرس الذي يتعدّاك', glimpse: 'نفعٌ يبقى لمن يأتي بعدك' },
      ],
    },
    starter: {
      prompt: 'أو ابدأ بمشهدك: اسحب صورة إلى هنا',
      dropping: 'أفلت الصورة هنا',
      choose: 'اختر صورة',
      camera: 'التقط بالكاميرا',
      cameraPreview: 'معاينة الكاميرا',
      cameraStarting: 'تُفتح الكاميرا…',
      shutter: 'التقط',
      cameraClose: 'أغلق الكاميرا',
      captureFailed: 'لم تُلتقط الصورة. حاول مرة أخرى أو اختر صورة.',
      cameraDenied: 'لم يُسمح بالكاميرا. يفتح هذا الزر كاميرا الهاتف، أو اختر صورة.',
      cameraUnavailable:
        'لا كاميرا متاحة في هذا المتصفح. يفتح هذا الزر كاميرا الهاتف إن وُجدت، أو اختر صورة.',
      cameraNeedsHttps:
        'تعمل الكاميرا الحية عبر اتصال آمن (https) فقط. يفتح هذا الزر كاميرا الهاتف، أو اختر صورة.',
      notImage: 'هذا الملف ليس صورة. اختر صورة بصيغة JPEG أو PNG أو WebP أو HEIC.',
    },
    /** Rows top to bottom, columns left to right of the photo (photo coordinates are physical). */
    positions: [
      ['أعلى يسار الصورة', 'أعلى وسط الصورة', 'أعلى يمين الصورة'],
      ['يسار وسط الصورة', 'وسط الصورة', 'يمين وسط الصورة'],
      ['أسفل يسار الصورة', 'أسفل وسط الصورة', 'أسفل يمين الصورة'],
    ],
  },

  evidence: {
    quran: 'القرآن',
    sunnah: 'السنة',
    openSource: 'افتح المصدر',
    openQuranpedia: 'افتح في قرآنبيديا',
    verified: 'نص موثّق من مصدره',
    verifyDorar: 'تحقق في الدرر',
    ruling: (ruling: string) => `حكم الدرر: ${ruling}`,
    /** The editor's reading of the ruling (decision 18), when dorar's own words are not in the answer. */
    classification: (classification: string) => `تصنيف المحرّر لحكم الدرر: ${classification}`,
    quranOpen: '﴿',
    quranClose: '﴾',
  },

  insight: {
    back: 'العودة إلى المشهد',
    seen: 'ما ظهر في الصورة:',
    explanation: 'شرح تبصرة',
    why: 'لماذا ظهر هذا؟',
    discuss: 'ناقش البصيرة',
    discussLimit: 'ثلاثة أسئلة',
    done: 'تمّ',
    share: 'شارك',
    photo: 'الصورة',
    photoCaption: 'تبقى الصورة أمامك وأنت تقرأ.',
  },

  /** The public page of a published insight (task 09.2): what a visitor without an account reads. */
  publicInsight: {
    unavailableTitle: 'تعذّر عرض البصيرة الآن',
    publishedOn: (day: string) => `نُشرت في ${day}`,
    authorLabel: 'صاحب البصيرة',
    stepTitle: 'خطوة صغيرة',
    callTitle: 'ابدأ بصيرتك أنت',
    callBody: 'صوّر مشهدًا من حولك، وانظر ما تقوله الآية والحديث عنه.',
    callSignIn: 'ادخل إلى حسابك',
  },

  victory: {
    title: 'اكتُشِف المعنى',
  },

  /** The personal world: a fog map of the learning path's regions (master prompt v2 §16-17). */
  world: {
    loading: 'نفتح خريطة عالمك…',
    unavailable: 'تعذّر فتح عالمك الآن. حاول بعد قليل.',
    retry: 'أعد المحاولة',
    summary: (opened: number, total: number) =>
      `انقشع الضباب عن ${opened} من ${total} مناطق. الضباب يدلّ على ما لم يُكتشف بعد، لا على نقص فيك.`,
    empty: {
      title: 'عالمك ينتظر أول بصيرة',
      body: 'يكسو الضباب خريطتك كلها الآن. حين تتمّ بصيرة ينقشع الضباب عن موضعها ويبقى لك. ابدأ بمشهد المطر الموثّق، أو صوّر مشهدك أنت.',
      cta: 'ابدأ بأول مشهد',
    },
    list: {
      title: 'المناطق',
      opened: (count: number) => (count === 1 ? 'بصيرة واحدة محفوظة' : `${count} بصائر محفوظة`),
      openedNoInsights: 'مفتوحة',
      fog: 'تحت الضباب',
      withTreasure: (state: string) => `${state}، فيها كنز ينتظر`,
    },
    map: {
      select: (name: string, state: string) => `${name}، ${state}`,
    },
    detail: {
      back: 'أغلق التفاصيل',
      fogBody:
        'ينقشع الضباب عن هذه المنطقة حين تتمّ بصيرة تنتمي إليها، فيظهر لك موضعها هنا. لا عجلة في ذلك.',
      lastVisit: (when: string) => `آخر زيارة: ${when}`,
      insights: 'بصائر هذا الموضع',
      insightMeta: (when: string) => `أُتمّت في ${when}`,
    },
    treasure: {
      title: 'كنز مخبوء',
      ready: 'ينتظرك في هذا الموضع شيء آخر يصل بما حفظته.',
      reveal: 'اكشف الكنز',
      revealing: 'نكشفه…',
      notReady: 'لم يحن وقته بعد. عد إلى هذا الموضع لاحقًا.',
      revealedTitle: 'كشفت كنزًا',
      unit: 'وحدة من المسار',
      verifiedSources: 'من المصادر المتحقَّق منها نفسها',
      quranReference: (surah: string, ayah: number) => `${surah} · ${ayah}`,
      hadithReference: (book: string, number: string) => `${book} · ${number}`,
    },
    threads: {
      title: 'الخيوط بين المواضع',
      lead: 'يصل خيطٌ بين موضعين حين تكون بينهما صلة مسجّلة، لا غير.',
      between: (a: string, b: string) => `بين «${a}» و«${b}»`,
      insights: 'البصائر الواصلة',
      none: 'لا خيوط بعد. تظهر حين تصل صلة مسجّلة بين موضعين.',
    },
  },

  /** «تمرينك»: practice ranks, streak, the daily quest, the sky of meanings and badges (decision 27). */
  practiceView: {
    title: 'تمرينك',
    lead: 'ما سجّله تمرينك من نظرات وبصائر وخطوات، لا غير. لا مقارنة بأحد، ولا حكم على إيمانك.',
    loading: 'نحمّل تمرينك…',
    unavailable: 'تعذّر تحميل تمرينك الآن. حاول بعد قليل.',
    retry: 'أعد المحاولة',
    back: 'ملفي',
    rank: {
      label: 'مرتبة التمرين',
      looks: (count: number) => `${count} نظرة مكتملة`,
      next: (title: string, minimum: number) => `المرتبة التالية «${title}» عند ${minimum} نظرة.`,
      top: 'بلغت أعلى مرتبة في التمرين، ويبقى التمرين مفتوحًا.',
      progressLabel: 'الطريق إلى المرتبة التالية',
    },
    streak: {
      label: 'سلسلة النظر',
      current: (days: number) => (days === 1 ? 'يوم واحد متتالٍ' : `${days} أيام متتالية`),
      best: (days: number) => `أطول سلسلة لك: ${days}`,
      week: 'آخر سبعة أيام',
      today: 'اليوم',
      looked: 'نظرت',
      notLooked: 'لم تنظر',
    },
    quest: {
      done: 'أتممت مهمة اليوم',
      pending: 'مهمة اليوم لم تكتمل بعد',
      daysDone: (days: number) => `أتممتها في ${days} أيام حتى الآن`,
    },
    sky: {
      title: 'سماء المعاني',
      count: (count: number) => {
        if (count === 0) {
          return 'لا معنى بعد';
        }
        return count === 1 ? 'معنى أضاء لك' : `${count} معاني أضاءت لك`;
      },
      label: 'المعاني التي أتممت بصائرها، نجمًا لكل معنى',
      star: (concept: string, count: number) =>
        count === 1 ? `${concept}، مرة واحدة` : `${concept}، ${count} مرات`,
      empty: 'لم يُضئ معنى بعد. حين تتمّ بصيرة يظهر معناها نجمًا في هذه السماء.',
      cta: 'ابدأ بأول مشهد',
    },
    badges: {
      title: 'علامات التمرين',
      earned: 'نلتها',
      locked: 'لم تُنل بعد',
      count: (earned: number, total: number) => `${earned} من ${total}`,
    },
    counts: {
      title: 'ما سجّلته',
      looks: 'نظرات مكتملة',
      completed: 'بصائر أتممتها',
      actionsDone: 'خطوات أقررت بها',
      places: 'مواضع في عالمك',
      treasures: 'كنوز كشفتها',
      questions: 'أسئلة سألتها',
    },
    teaser: {
      body: 'مرتبة التمرين وسلسلة النظر ومهمة اليوم وسماء المعاني والعلامات، كلها في صفحة واحدة.',
      open: 'افتح تمرينك',
    },
  },

  progress: {
    label: 'مراحل إعداد البصيرة',
    stages: {
      scene: 'أفهم المشهد',
      evidence: 'أبحث عن الأدلة',
      verify: 'أتحقق من المصادر',
      compose: 'أعدّ بصيرتك',
    },
    status: {
      done: 'تمّت',
      current: 'الآن',
      pending: 'لاحقًا',
    },
    queued: 'ننتظر دور مشهدك',
    complete: 'بصيرتك جاهزة',
    slow: 'ما زلنا نعمل على طلبك، وقد يستغرق وقتًا أطول من المعتاد.',
    cancel: 'ألغِ',
  },

  step: {
    title: 'خطوة صغيرة',
    defer: 'سأفعله لاحقًا',
    saving: 'أحفظ ما صرّحت به…',
    saved: 'سُجّل ما صرّحت به.',
    deferred: 'أجّلت الخطوة، وستجدها هنا حين تعود.',
  },

  disclosure: {
    ai: 'تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا',
  },

  /**
   * What a failed request means for the reader, one message per stable API
   * error code (the API's ErrorCode). The cause is never put on the reader
   * when it is ours (tajriba §7).
   */
  errors: {
    network: 'تعذّر الوصول إلى تبصرة. تحقّق من اتصالك ثم أعد المحاولة.',
    server: 'حدث خطأ من جهتنا، لا من جهتك. أعد المحاولة بعد قليل.',
    rateLimited: (wait: string) => `محاولات كثيرة في وقت قصير. أعد المحاولة بعد ${wait}.`,
    rateLimitedSoon: 'محاولات كثيرة في وقت قصير. انتظر قليلًا ثم أعد المحاولة.',
    origin: 'لم نقبل الطلب لأنه لم يصل من صفحات تبصرة نفسها. حدّث الصفحة ثم أعد المحاولة.',
    unauthorized: 'انتهت جلستك. ادخل من جديد لتكمل.',
    invalidCredentials:
      'البريد وكلمة المرور لا يتطابقان مع حساب لدينا. تحقّق منهما، أو استعد كلمة المرور.',
    accountDisabled: 'هذا الحساب موقوف، فلا يمكن الدخول به.',
    emailTaken: 'لهذا البريد حساب من قبل. ادخل به، أو استعد كلمة المرور إن نسيتها.',
    invalidToken: 'هذا الرابط غير صالح: ربما استُعمل من قبل أو انتهت مدته.',
    emailNotVerified: 'أكّد بريدك أولًا من الرابط الذي أرسلناه إليك.',
    consentNotAllowed: 'لا نحفظ صور من صرّح بأنه دون 13 عامًا، فلا يمكن تفعيل هذا الخيار.',
    googleNotConfigured: 'الدخول بحساب Google غير متاح الآن. ادخل بالبريد الإلكتروني.',
    validation: 'بعض الحقول تحتاج تصحيحًا.',
    legalStale: 'تغيّرت شروط الاستخدام أو سياسة الخصوصية للتو. راجعهما ثم وافق من جديد.',
    legalRequired: 'وافق على شروط الاستخدام وسياسة الخصوصية في نسختهما الحالية لتتابع.',
    /** Minutes, with the Arabic counted noun: دقيقة، دقيقتين، ٣ إلى ١٠ دقائق، ١١ فأكثر دقيقة. */
    minutes: (count: number) => {
      if (count <= 1) {
        return 'دقيقة';
      }
      if (count === 2) {
        return 'دقيقتين';
      }
      return count <= 10 ? `${count} دقائق` : `${count} دقيقة`;
    },
  },

  auth: {
    fields: {
      email: 'البريد الإلكتروني',
      password: 'كلمة المرور',
      newPassword: 'كلمة المرور الجديدة',
      passwordHint: 'عشرة أحرف على الأقل.',
      displayName: 'الاسم الذي نناديك به',
      displayNameHint: 'يظهر في ملفك، وبجانب ما تنشره لاحقًا.',
      showPassword: 'أظهر كلمة المرور',
      hidePassword: 'أخفِ كلمة المرور',
    },
    validation: {
      emailMissing: 'اكتب بريدك الإلكتروني.',
      emailInvalid: 'هذا لا يبدو بريدًا إلكترونيًا. مثال: name@example.com',
      passwordMissing: 'اكتب كلمة المرور.',
      passwordShort: 'كلمة المرور قصيرة: عشرة أحرف على الأقل.',
      passwordLong: 'كلمة المرور أطول مما نقبل. اختصرها قليلًا؛ الحرف العربي يُحسب بحرفين.',
      nameMissing: 'اكتب الاسم الذي نناديك به.',
      nameLong: 'الاسم أطول من 60 حرفًا. اختصره قليلًا.',
      nameInvalid: 'في الاسم رموز لا نقبلها. اكتبه بحروف عادية.',
    },
    optional: 'الحساب اختياري؛ التجربة كلها متاحة لك دونه.',
    backToScene: 'عد إلى المشهد',
    signIn: {
      metaTitle: 'الدخول',
      metaDescription: 'ادخل إلى حسابك في تبصرة لتجد بصائرك ومسارك على أي جهاز.',
      title: 'ادخل إلى تبصرة',
      lead: 'لتجد بصائرك ومسارك حيث تركتها، على أي جهاز.',
      submit: 'ادخل',
      submitting: 'أدخلك…',
      forgot: 'نسيت كلمة المرور؟',
      noAccount: 'ليس لك حساب؟',
      createAccount: 'أنشئ حسابًا',
      signedInAs: (name: string) => `أنت داخل باسم ${name}.`,
      openProfile: 'افتح ملفي',
    },
    signUp: {
      metaTitle: 'إنشاء حساب',
      metaDescription: 'أنشئ حسابًا في تبصرة ليحفظ مسارك وبصائرك، فتجدها متى عدت.',
      title: 'أنشئ حسابك',
      lead: 'ليحفظ مسارك وبصائرك، فتجدها متى عدت ومن أي جهاز.',
      submit: 'أنشئ الحساب',
      submitting: 'أنشئ حسابك…',
      haveAccount: 'لك حساب؟',
      signIn: 'ادخل',
      doneTitle: 'أُنشئ حسابك',
      doneBody: (email: string) =>
        `طلبنا إرسال رابط تأكيد إلى ${email}. تبصرة كلها متاحة لك الآن، والتأكيد يلزم قبل أن تنشر شيئًا للناس.`,
      doneHint:
        'إن لم تصلك الرسالة خلال دقائق، فافحص مجلد الرسائل غير المرغوب فيها، أو اطلب رابطًا جديدًا من «ملفي».',
      continue: 'تابع',
    },
    google: {
      action: 'تابع بحساب',
      name: 'Google',
      divider: 'أو بالبريد الإلكتروني',
      or: 'أو',
      /** Where the API's Google callback sends a failure: /signin?error=<code> (docs/AUTH.md). */
      errors: {
        google_state: 'انتهت محاولة الدخول بحساب Google أو بدأت في متصفح آخر. ابدأ من جديد.',
        google_denied: 'ألغيت الدخول في صفحة Google، ولم يتغير شيء.',
        google_failed: 'لم نتمكن من إتمام الدخول بحساب Google. أعد المحاولة، أو ادخل بالبريد.',
        account_disabled: 'هذا الحساب موقوف، فلا يمكن الدخول به.',
      },
    },
    verify: {
      metaTitle: 'تأكيد البريد',
      metaDescription: 'أكّد بريدك الإلكتروني في تبصرة من الرابط الذي وصلك.',
      title: 'تأكيد بريدك',
      lead: 'خطوة واحدة: اضغط الزر ليتأكد بريدك.',
      confirm: 'أكّد بريدي',
      confirming: 'أؤكّد…',
      done: 'تأكّد بريدك. شكرًا لك.',
      missing: 'لم نجد رمز التأكيد في الرابط. افتح الرابط من رسالة البريد كما هو، كاملًا.',
      resendTitle: 'اطلب رابطًا جديدًا',
      resend: 'أرسل الرابط',
      resending: 'أرسل…',
      resent: 'إن كان لهذا البريد حساب لم يُؤكَّد بعد، فستصله رسالة فيها رابط جديد خلال دقائق.',
      openProfile: 'افتح ملفي',
    },
    forgot: {
      metaTitle: 'استعادة كلمة المرور',
      metaDescription: 'اطلب رابطًا تختار به كلمة مرور جديدة لحسابك في تبصرة.',
      title: 'استعادة كلمة المرور',
      lead: 'اكتب بريدك، ونرسل إليه رابطًا تختار به كلمة مرور جديدة.',
      submit: 'أرسل الرابط',
      submitting: 'أرسل…',
      sent: 'إن كان لهذا البريد حساب، فستصله رسالة فيها رابط لاختيار كلمة مرور جديدة. يعمل الرابط مرة واحدة ولمدة محدودة.',
      backToSignIn: 'عد إلى الدخول',
    },
    reset: {
      metaTitle: 'كلمة مرور جديدة',
      metaDescription: 'اختر كلمة مرور جديدة لحسابك في تبصرة.',
      title: 'كلمة مرور جديدة',
      lead: 'اختر كلمة مرور جديدة لحسابك. تنتهي بعدها جلساتك على الأجهزة الأخرى.',
      submit: 'احفظ كلمة المرور',
      submitting: 'أحفظ…',
      done: 'حُفظت كلمة المرور الجديدة، وأُنهيت جلساتك على الأجهزة الأخرى. ادخل بها الآن.',
      missing:
        'لم نجد رمز الاستعادة في الرابط. افتح الرابط من رسالة البريد كما هو، أو اطلب رابطًا جديدًا.',
      requestNew: 'اطلب رابطًا جديدًا',
      signIn: 'ادخل',
    },
    signOut: {
      action: 'اخرج',
      busy: 'أخرجك…',
      done: 'خرجت من حسابك على هذا الجهاز.',
    },
    /**
     * Accepting the terms of use and the privacy policy (owner decision 35):
     * one unticked box, each text linked, at sign-up and again when a text changes.
     */
    legal: {
      before: 'أوافق على ',
      terms: 'شروط الاستخدام',
      and: ' و',
      privacy: 'سياسة الخصوصية',
      unavailable: 'تعذّر تحميل نسخة الشروط والخصوصية الآن، فلا يمكن إنشاء حساب في هذه اللحظة.',
      retry: 'أعد المحاولة',
      gate: {
        title: 'قبل أن تتابع',
        body: 'نحتاج موافقتك على شروط الاستخدام وسياسة الخصوصية في نسختهما الحالية لتتابع بحسابك. اقرأهما متى شئت من الرابطين.',
        accept: 'أوافق وأتابع',
        accepting: 'أسجّل موافقتك…',
        decline: 'لا أوافق، أخرجني',
      },
    },
    /** After the first completed insight (master prompt v2 §4.7, tajriba §7). */
    invitation: {
      title: 'هل تحفظ ما تعلّمته لنواصل من هنا؟',
      body: 'بحساب تجد بصائرك ومسارك متى عدت. الحساب اختياري، والتجربة كلها متاحة دونه.',
      save: 'احفظ مساري',
      guest: 'أتابع كضيف',
    },
  },

  /** The optional profile (master prompt v2 §5): every answer can be skipped and stays `unknown`. */
  profile: {
    title: 'عنك',
    statement: 'نستخدم اختياراتك وبصائرك السابقة لتقديم تعلّم يناسبك، ويمكنك تعطيل ذلك.',
    optional: 'كل سؤال اختياري. لا نستنتج شيئًا عنك من صورك أو اسمك أو مكانك.',
    skip: 'تخطَّ',
    saving: 'أحفظ…',
    saved: 'حُفظ.',
    flow: {
      title: 'كيف تحب أن تتعلم وتتأمل؟',
      progress: (step: number, total: number) => `السؤال ${step} من ${total}`,
      saveAndContinue: 'احفظ وتابع',
      skipAll: 'تخطَّ الأسئلة كلها',
      done: 'شكرًا لك. نراعي اختياراتك في الشرح، وتغيّرها متى شئت من «ملفي».',
    },
    goals: {
      label: 'ما الذي تريده من تبصرة؟',
      hint: 'اختر ما يناسبك، واحدًا أو أكثر، أو لا شيء.',
      options: {
        discover_islam: 'التعرّف إلى الإسلام',
        reflection: 'التفكر',
        learn_quran_sunnah: 'تعلّم القرآن والسنة',
        live_values: 'العمل بالقيم',
        research: 'البحث',
        teaching: 'التعليم',
        curiosity: 'الفضول والاستكشاف',
      },
    },
    knowledge: {
      label: 'ما معرفتك السابقة بالقرآن والسنة؟',
      options: {
        new: 'جديد على الموضوع',
        general: 'معرفة عامة',
        advanced: 'متقدم',
        specialist: 'متخصص',
        unknown: 'أفضّل عدم الإجابة',
      },
    },
    age: {
      label: 'فئتك العمرية',
      hint: 'لا نسألك عن تاريخ ميلادك أبدًا.',
      options: {
        under_13: 'أقل من 13',
        '13_17': 'من 13 إلى 17',
        '18_24': 'من 18 إلى 24',
        '25_39': 'من 25 إلى 39',
        '40_59': 'من 40 إلى 59',
        '60_plus': '60 فأكثر',
        unknown: 'أفضّل عدم الإجابة',
      },
    },
    religion: {
      label: 'خلفيتك الدينية',
      hint: 'اختياري. لا يراه أحد غيرك، ولا نستنتجه من شيء.',
      options: {
        muslim: 'من المسلمين',
        non_muslim: 'من غير المسلمين',
        unknown: 'أفضّل عدم الإجابة',
      },
    },
    gender: {
      label: 'الجنس',
      hint: 'اختياري. لا يراه أحد غيرك، ولا نستنتجه من صورة أو اسم.',
      options: {
        man: 'ذكر',
        woman: 'أنثى',
        unknown: 'أفضّل عدم الإجابة',
      },
    },
  },

  settings: {
    device: 'على هذا الجهاز',
    account: 'في حسابك',
    saved: 'حُفظ اختيارك.',
    personalization: {
      label: 'التخصيص',
      hint: 'نرتّب الشرح والخطوة العلمية بحسب ما اخترته. لا يتغير النص ولا الدليل.',
    },
    memory: {
      label: 'الذاكرة',
      hint: 'نتذكر بصائرك السابقة لنقترح خطوة تناسبك ولا نكرر عليك.',
    },
    photos: {
      label: 'حفظ صوري',
      hint: 'نحفظ صورة كل بصيرة تحفظها، في مخزن خاص بلا بيانات الموقع، وتُحذف مع البصيرة ومع الحساب. لا تُحفظ صورة مشهد حساس.',
      under13: 'لا نحفظ صور من صرّح بأنه دون 13 عامًا.',
    },
  },

  /** Shown wherever a rank, a badge or a streak appears (GAMIFICATION.md §0). */
  practice: {
    disclaimer:
      'هذه علامات على التمرين والمواظبة لا على الإيمان ولا على القبول؛ تُحتسب من أفعالك المسجلة فقط.',
  },

  /** The full-screen cookie consent (owner decision 32). */
  consent: {
    title: 'اختر ما تسمح به',
    lead: 'تحتاج تبصرة ملفات ضرورية لتعمل وتحفظ دخولك. وبإذنك وحده نقيس كيف تُستعمل الصفحات لنحسّنها.',
    never:
      'لا نرسل إلى أي أداة قياس صورك، ولا ما تكتبه، ولا نصوص البصائر والآيات والأحاديث، ولا موقعك، ولا بريدك.',
    free: 'رفضك لا يغلق شيئًا؛ تبصرة كلها تعمل كما هي. وتغيّر اختيارك متى شئت من أسفل كل صفحة أو من «ملفي».',
    acceptAll: 'قبول الكل',
    rejectAll: 'رفض الكل',
    customise: 'تخصيص',
    customiseTitle: 'اختر فئة فئة',
    always: 'مفعّلة دائمًا',
    save: 'احفظ اختياري',
    back: 'رجوع',
    close: 'أغلق دون تغيير',
    saving: 'أحفظ اختيارك…',
    saveFailed: 'تعذّر حفظ اختيارك الآن، فلم نفعّل شيئًا. أعد المحاولة، أو اختر «رفض الكل» لتكمل.',
    policyLoading: 'نحمّل تفاصيل الفئات…',
    policyFailed: 'تعذّر تحميل تفاصيل الفئات الآن.',
    retry: 'أعد المحاولة',
    reaskVersion: 'حدّثنا سياسة ملفات تعريف الارتباط، فنسألك من جديد.',
    reaskTime: 'مضى وقت على اختيارك، فنسألك من جديد كما وعدنا.',
    version: (version: string) => `نسخة السياسة: ${version}`,
    allowed: 'مسموح',
    notAllowed: 'غير مسموح',
    categoryNames: {
      necessary: 'الضرورية',
      analytics: 'قياس الاستعمال',
      behaviour: 'السلوك والخرائط الحرارية',
    },
    undecided: 'لم تختر بعد.',
    decidedOn: (date: string) => `اخترت في ${date}.`,
    change: 'غيّر اختياراتي',
  },

  /** «أطلس بصائر العالم» (docs/spec/extension-atlas-camera.md): published insights at approximate points. */
  atlas: {
    title: 'أطلس بصائر العالم',
    lead: 'بصائر نشرها أصحابها في أماكنها التقريبية. تصفّح العالم دون أن تمنح موقعك.',
    mapLabel: 'خريطة الأطلس',
    /** Joins a place's labels (place, region, country) the way Arabic lists them. */
    mapUnsupported:
      'لا يدعم هذا المتصفح أو الجهاز عرض الخريطة (يلزم WebGL2). تبقى النتائج في القائمة بجانبها.',
    joinLabels: (parts: readonly (string | null | undefined)[]) => parts.filter(Boolean).join('، '),
    attribution: 'بلاط الخريطة من OpenFreeMap، بيانات OpenStreetMap.',
    searchHere: 'ابحث في هذه المنطقة',
    nearMe: 'قريب مني',
    nearMeHint:
      'يحرّك الخريطة إلى موضعك على جهازك؛ موضعك نفسه لا يُرسل إلى تبصرة، وما يُرسل عند البحث هو نطاق الخريطة المعروض.',
    nearMeDenied: 'لم يُمنح إذن الموقع، فتبقى الخريطة حيث هي. يمكنك البحث عن مكان.',
    nearMeUnavailable: 'لا يستطيع هذا الجهاز تحديد موضعه الآن.',
    search: 'ابحث عن مدينة أو مكان',
    searchForm: 'البحث عن مكان',
    searchPlaceholder: 'اسم مدينة أو مكان',
    searching: 'نبحث…',
    noPlaces: 'لم نجد مكانًا بهذا الاسم.',
    loading: 'نحمّل البصائر…',
    failed: 'تعذّر تحميل البصائر الآن.',
    retry: 'أعد المحاولة',
    empty: 'لا توجد بصائر منشورة في هذه المنطقة بعد.',
    emptyHint: 'وسّع المنطقة أو أضف بصيرة من عالمك.',
    truncated: 'في هذه المنطقة بصائر أكثر مما نعرضه؛ قرّب الخريطة لترى المزيد.',
    count: (count: number) => {
      if (count === 0) {
        return 'لا بصائر';
      }
      if (count === 1) {
        return 'بصيرة واحدة';
      }
      return count === 2 ? 'بصيرتان' : count <= 10 ? `${count} بصائر` : `${count} بصيرة`;
    },
    inView: 'في هذه المنطقة',
    filters: {
      label: 'المرشحات',
      period: 'الفترة',
      periods: { all: 'كل الوقت', week: 'آخر أسبوع', month: 'آخر شهر', year: 'آخر سنة' },
      country: 'البلد',
      anyCountry: 'كل البلدان',
      concept: 'الموضوع',
      anyConcept: 'كل المواضيع',
      /** A concept filter comes from an entry's own page («بصائر بالمعنى نفسه»); the ids carry no name yet. */
      conceptActive: 'بالمعنى نفسه: بصائر تشترك في معنى البصيرة التي جئت منها.',
      clearConcept: 'امسح المعنى',
      scope: 'ما يُعرض',
      scopes: { public: 'بصائر الناس', mine: 'بصائري المنشورة' },
      clear: 'امسح المرشحات',
    },
    /** The owner's own entries, from every state, beside the public map (extension §4). */
    mine: {
      list: 'بصائري على الأطلس',
      loading: 'نحمّل بصائرك…',
      empty: 'لم تضع بصيرة على الأطلس بعد.',
      emptyHint: 'افتح بصيرة في عالمك واختر «انشر على الخريطة».',
      review: 'راجع الموضع',
    },
    list: 'قائمة البصائر في المنطقة',
    marker: (title: string) => `افتح ${title}`,
    cluster: (count: number) => `مجموعة من ${count} بصائر، قرّب لتفصلها`,
    card: {
      open: 'افتح البصيرة',
      openPost: 'افتح المنشور في تواصل',
      place: 'المكان',
      by: (name: string) => `نشرها ${name}`,
      publishedAt: (when: string) => `نُشرت في ${when}`,
      close: 'أغلق',
      placePage: 'ذاكرة المكان',
    },
    entry: {
      back: 'العودة إلى الأطلس',
      notFound: { title: 'لم نجد هذه البصيرة', description: 'ربما لم تُنشر بعد، أو لا تُعرض.' },
      gone: {
        title: 'سُحبت هذه البصيرة من الأطلس',
        description: 'سحبها صاحبها، فلم يبق منها إلا هذا العنوان.',
      },
      mapLabel: 'موضع البصيرة التقريبي',
      locationNote:
        'النقطة مركز منطقة تقريبية حُسب على الخادم، لا موضع التصوير الحقيقي، كما حدّده صاحب البصيرة ولم يُتحقق منه. الموقع قرينة جغرافية لا دليل ديني.',
      explanation: 'شرح تبصرة',
      step: 'خطوة صغيرة',
      sameMeaning: 'بصائر بالمعنى نفسه على الخريطة',
    },
    /** The share line of a place page. */
    placeDescription: (label: string) => `البصائر التي نشرها الناس في ${label} على أطلس تبصرة.`,
    place: {
      title: (label: string) => `ذاكرة المكان: ${label}`,
      lead: 'ما رآه الناس من معانٍ في هذا المكان، كل بصيرة بما تضيفه.',
      loading: 'نحمّل المكان…',
      notFound: {
        title: 'لا بصائر في هذا المكان بعد',
        description: 'حين تُنشر بصيرة فيه تظهر هنا.',
      },
      more: 'اعرض المزيد',
      end: 'هذا كل ما نُشر في هذا المكان حتى الآن.',
      showOnMap: 'اعرض على الخريطة',
    },
    publish: {
      title: 'أضف بصيرتك إلى الأطلس',
      lead: 'تُعرض بصيرتك على خريطة العالم في موضع تقريبي يحسبه الخادم؛ موضعك الدقيق يبقى لك وحدك.',
      noInsight: {
        title: 'اختر بصيرة أولًا',
        description: 'يبدأ النشر من بصيرة محفوظة في عالمك.',
        world: 'افتح عالمي',
      },
      signIn: 'ادخل لتضيف بصيرتك إلى الأطلس.',
      verify: 'أكّد بريدك قبل أن تنشر شيئًا للناس.',
      identityFirst: 'اختر هويتك العامة أولًا؛ يظهر اسمك العام مع البصيرة على الخريطة.',
      where: 'أين التُقطت الصورة؟',
      whereHint: 'لا نعيّن موقعك الحالي تلقائيًا لصورة قديمة. اختر بنفسك.',
      useDevice: 'استعمل موضعي الآن',
      useDeviceHint: 'لصورة التُقطت هنا الآن. يُحفظ الموضع لك وحدك.',
      searchPlace: 'ابحث عن مكان',
      tapMap: 'أو المس الخريطة لتحدد الموضع',
      chosen: 'الموضع المختار',
      meaning: 'ما الذي تشير إليه النقطة؟',
      meanings: { capture_point: 'موضع التقاط الصورة', public_place: 'مكان عام اخترته' },
      preview: 'هكذا يظهر موضعك للناس',
      previewHint:
        'المنطقة المظللة والنقطة في وسطها هما ما يُنشر؛ موضعك الدقيق لا يظهر لغيرك، ويبقى لك في حسابك.',
      precision: 'الدقة',
      placeLabel: 'يُسمّى المكان',
      noPlace: 'لا مكان مأهول قريب في بيانات الخريطة؛ تُعرض النقطة بلا اسم.',
      save: 'احسب الموضع التقريبي',
      saving: 'أحسب…',
      saved: 'حُسب موضعك التقريبي. راجعه ثم انشر.',
      publish: 'انشر على الأطلس',
      publishing: 'أنشر…',
      published: 'نُشرت بصيرتك على الأطلس.',
      withdraw: 'اسحب من الأطلس',
      withdrawing: 'أسحب…',
      withdrawn: 'سُحبت بصيرتك من الأطلس ونُسي موضعها الدقيق.',
      withdrawTitle: 'سحب البصيرة من الأطلس؟',
      withdrawLead:
        'تختفي النقطة من الخريطة والبحث في الحال، ويُنسى موضعها الدقيق. تبقى البصيرة في عالمك.',
      withdrawConfirm: 'اسحب',
      cancel: 'تراجع',
      status: {
        draft: 'موضع محفوظ، لم يُنشر',
        published: 'منشورة على الأطلس',
        pending_review: 'مخفية حتى يراجعها مشرف',
        removed: 'أزالها مشرف',
        withdrawn: 'مسحوبة',
      },
      notPublishable:
        'لا يمكن وضع هذه البصيرة على الأطلس: تُنشر البصائر المتحقَّقة التي تملكها وحدها.',
      open: 'افتحها على الأطلس',
      loadingMine: 'نتحقق مما حفظته…',
      noLocation: 'لم تحدد موضعًا بعد.',
      photo: 'أرفق الصورة',
      photoHint:
        'تصير صورة مشهدك عامة مع النقطة على الأطلس لكل من يفتحها، وتُحذف نسختها العامة حين تسحبها.',
      withPhoto: 'تُعرض الصورة مع النقطة',
    },
    /**
     * «اكتشف البصائر حولك» (extension §5–7): published entries near the device,
     * listed by distance over the camera's live view, with the direction of each
     * when the sensors give a heading. The view is never read or sent; what is
     * shown is recorded knowledge, never an analysis of what the camera sees.
     */
    camera: {
      title: 'اكتشف البصائر حولك',
      description:
        'وجّه كاميرا هاتفك لترى البصائر التي نشرها الناس قريبًا منك، في منطقتها التقريبية.',
      open: 'اكتشف بالكاميرا',
      lead: 'بصائر منشورة قريبة منك تظهر فوق بث الكاميرا، كل واحدة في منطقتها التقريبية.',
      needs: {
        heading: 'ما يحتاجه الاستكشاف',
        camera: 'الكاميرا: لترى ما حولك خلف التسميات. لا تُحفظ منها لقطة ولا تُرسل إلى تبصرة.',
        location: 'الموقع: ليُعرف نطاق البحث. يُرسل نطاق تقريبي حول موضعك، لا موضعك نفسه.',
        direction: 'الاتجاه، إن شئت: ليشير سهم نحو منطقة كل بصيرة. يبقى على جهازك.',
      },
      start: 'ابدأ الاستكشاف',
      starting: 'نطلب الأذونات…',
      showOnMap: 'اعرض على الخريطة',
      stageLabel: 'بث الكاميرا وتسميات البصائر القريبة',
      nearbyLabel: 'بصائر قريبة',
      notLive: 'ما يظهر بصائر سجّلها أصحابها من قبل، لا تحليلًا لما تراه الكاميرا الآن.',
      mode: {
        area: 'العرض بحسب المنطقة',
        direction: 'العرض بالاتجاه التقريبي',
        chosen: 'استكشاف المنطقة المختارة',
      },
      cameraDenied: 'لم يُمنح إذن الكاميرا، فتبقى القائمة والخريطة. يمكنك منحه من إعدادات المتصفح.',
      cameraUnavailable:
        'لا تتوفر الكاميرا في هذا المتصفح أو عبر هذا الاتصال، فتبقى القائمة والخريطة.',
      cameraPaused: 'توقفت الكاميرا حين غادرت الصفحة.',
      resumeCamera: 'أعد تشغيل الكاميرا',
      stopCamera: 'أوقف الكاميرا',
      locating: 'نحدد منطقتك…',
      locationDenied: 'لم يُمنح إذن الموقع. اختر مكانًا لتستكشف منطقته.',
      locationUnavailable: 'لا يستطيع هذا الجهاز تحديد موضعه الآن. اختر مكانًا لتستكشف منطقته.',
      lowAccuracy: 'دقة الموقع منخفضة، فنعرض البصائر بحسب المنطقة.',
      enableHeading: 'فعّل الاتجاه',
      headingWaiting: 'ننتظر قراءة الاتجاه…',
      headingDenied: 'لم يُمنح إذن حساسات الاتجاه؛ العرض بحسب المنطقة.',
      headingUnavailable: 'لا يعطي هذا الجهاز اتجاهًا مطلقًا؛ العرض بحسب المنطقة.',
      headingStale: 'انقطعت قراءة الاتجاه؛ العرض بحسب المنطقة.',
      headingNote:
        'السهم يشير إلى المنطقة التقريبية للبصيرة، لا إلى شيء بعينه، ولا يعني أن الطريق إليها مفتوح.',
      near: 'أنت بالقرب من منطقتها',
      inArea: 'في هذه المنطقة',
      about: (distance: string) => `نحو ${distance}`,
      meters: (count: number) => `${count} م`,
      kilometers: (count: string) => `${count} كم`,
      sectors: { ahead: 'أمامك', right: 'عن يمينك', behind: 'خلفك', left: 'عن يسارك' },
      toward: (sector: string) => `الاتجاه التقريبي: ${sector}`,
      arrow: (sector: string) => `سهم نحو منطقة البصيرة، ${sector}`,
      inViewMark: 'في اتجاه الكاميرا',
      list: 'قائمة البصائر القريبة',
      listHeading: 'الأقرب إليك',
      showAll: (count: number) => `اعرض الكل (${count})`,
      showNearest: 'اعرض الأقرب فقط',
      loading: 'نحمّل البصائر القريبة…',
      empty: 'لا توجد بصائر منشورة قريبة بعد.',
      emptyHint: 'كن أول من يضيف بصيرة، أو وسّع المنطقة.',
      widen: 'وسّع المنطقة',
      widest: 'هذا أوسع نطاق نبحث فيه.',
      addOwn: 'أضف بصيرة',
      retry: 'أعد المحاولة',
      openEntry: 'افتح البصيرة',
      statusLabel: 'حالة الاستكشاف',
    },
  },

  /**
   * «تبصرة تواصل» (docs/SOCIAL_NETWORK.md). Posts are made from verified
   * insights; the author's own words are always labelled as theirs. A like is
   * an «أثر», a gentle glow, never a score (DESIGN_DECISION.md «Game feel»).
   */
  community: {
    title: 'تبصرة تواصل',
    lead: 'بصائر موثّقة ينشرها أصحابها؛ تتابعهم، وتحفظ ما ينفعك، وتعلّق بأدب.',
    tabsLabel: 'أقسام تواصل',
    tabs: {
      forYou: 'لك',
      following: 'أتابع',
      latest: 'الأحدث',
      mine: 'منشوراتي',
      saved: 'محفوظاتي',
    },
    /** The share line of a public profile: the name and what the page holds, nothing more. */
    profileDescription: (name: string) => `بصائر ${name} المنشورة في تبصرة تواصل.`,
    publishCall: 'انشر بصيرة من عالمك',
    publishHint: 'تُنشر البصيرة كما تحقّقت تبصرة منها، وتضيف إليها كلماتك إن شئت.',
    loading: 'نحمّل المنشورات…',
    loadMore: 'اعرض المزيد',
    loadingMore: 'نحمّل المزيد…',
    end: 'هذا كل ما نُشر حتى الآن.',
    failed: 'تعذّر تحميل المنشورات الآن.',
    retry: 'أعد المحاولة',
    empty: {
      no_posts: 'لا منشورات هنا بعد.',
      follows_nobody: 'لا تتابع أحدًا بعد. حين تتابع أعضاء تظهر بصائرهم هنا.',
      saved: 'لم تحفظ منشورًا بعد. احفظ ما ينفعك من «لك» أو «الأحدث».',
      mine: 'لم تنشر بصيرة بعد. افتح بصيرة محفوظة في عالمك واختر «انشر في تواصل».',
    },
    signInToFollow: 'ادخل لترى بصائر من تتابعهم.',
    signIn: 'ادخل',
    off: 'تبصرة تواصل غير متاح الآن.',
    post: {
      openPost: 'افتح المنشور',
      reveal: 'اعرض الآية والحديث',
      revealQuran: 'اعرض الآية',
      revealHadith: 'اعرض الحديث',
      revealNone: 'اعرض الدليل',
      hide: 'أخفِ الآية والحديث',
      evidenceLabel: 'الدليل الموثّق',
      verseAlone: 'تستند هذه البصيرة إلى الآية وحدها.',
      hadithAlone: 'تستند هذه البصيرة إلى الحديث وحده.',
      noEvidence: 'لا نص موثّق يُعرض مع هذه البصيرة الآن.',
      reflection: 'كلمات الكاتب',
      reflectionNote: 'هذه كلمات الكاتب نفسه، ليست نصًا موثّقًا.',
      looksLikeScripture: 'يبدو هذا النص كآية أو حديث، وهو من كلمات الكاتب ولم تتحقق منه تبصرة.',
      explanation: 'شرح تبصرة',
      step: 'خطوة صغيرة',
      like: 'أثر',
      liked: 'تركت أثرًا',
      unlike: 'ارفع أثرك',
      likeCount: (count: number) => (count === 1 ? 'أثر واحد' : `${count} آثار`),
      comments: 'التعليقات',
      commentCount: (count: number) => {
        if (count === 0) {
          return 'لا تعليقات';
        }
        if (count === 1) {
          return 'تعليق واحد';
        }
        return count === 2 ? 'تعليقان' : count <= 10 ? `${count} تعليقات` : `${count} تعليقًا`;
      },
      save: 'احفظ',
      saved: 'محفوظ',
      unsave: 'ألغِ الحفظ',
      more: 'المزيد',
      why: 'لماذا أرى هذا؟',
      visibility: { public: 'للجميع', followers: 'للمتابعين' },
      status: {
        draft: 'مسودة',
        pending_review: 'قيد المراجعة',
        published: 'منشور',
        rejected: 'لم يُقبل',
        removed: 'أُزيل',
      },
      statusHint: 'لا يرى هذه الحالة غيرك.',
      publishedAt: (when: string) => `نُشر في ${when}`,
      createdAt: (when: string) => `أُنشئ في ${when}`,
      authorLink: (name: string) => `صفحة ${name}`,
      quranReference: (surahName: string, ayah: number) => `سورة ${surahName} · ${ayah}`,
      hadithReference: (collectionName: string, number: string) => `${collectionName} · ${number}`,
    },
    why: {
      title: 'لماذا أرى هذا؟',
      reason: 'سبب ظهور هذا المنشور:',
      lead: 'ترتيب «لك» حساب بسيط من أربعة مدخلات تعرفها كلها، لا نموذج ولا شيء من ملفك:',
      inputs: [
        'الجدّة: المنشور الأحدث يسبق الأقدم.',
        'المتابعة: منشور من تتابعه يتقدم قليلًا.',
        'التنويع: موضوع تكرر في القائمة يتأخر قليلًا.',
        'ما لقيته: منشور تركت فيه أثرًا أو حفظته أو علّقت عليه يتأخر.',
      ],
      never: 'لا يدخل في الترتيب دينك ولا عمرك ولا جنسك ولا أي إجابة من ملفك، ولا يتعلّم من نقراتك.',
      personalisation: 'إن أوقفت التخصيص من «ملفي» بقي الترتيب على الجدّة والتنويع وحدهما.',
      settings: 'افتح «ملفي»',
    },
    reactions: {
      signIn: 'ادخل لتترك أثرًا أو تحفظ منشورًا.',
      verify: 'أكّد بريدك لتترك أثرًا.',
    },
    comments: {
      title: 'التعليقات',
      loading: 'نحمّل التعليقات…',
      failed: 'تعذّر تحميل التعليقات الآن.',
      empty: 'لا تعليقات بعد.',
      loadMore: 'اعرض مزيدًا من التعليقات',
      write: 'اكتب تعليقًا',
      writeReply: (name: string) => `اكتب ردًا على ${name}`,
      send: 'أرسل',
      sending: 'أرسل…',
      reply: 'ردّ',
      cancelReply: 'ألغِ الرد',
      delete: 'احذف',
      deleting: 'أحذف…',
      deleted: 'حُذف تعليقك.',
      mine: 'تعليقك',
      limit: (max: number) => `${max} حرفًا على الأكثر.`,
      signIn: 'ادخل لتعلّق.',
      verify: 'أكّد بريدك قبل أن تعلّق.',
      identity: 'اختر اسمك العام قبل أن تعلّق.',
      chooseIdentity: 'اختر اسمك العام',
      pending: 'تعليقك يراجعه مشرف قبل أن يراه غيرك.',
    },
    report: {
      action: 'بلّغ',
      title: 'بلّغ عن هذا',
      lead: 'يصل بلاغك إلى المشرفين وحدهم، ولا يُخبر به صاحب المنشور.',
      reason: 'السبب',
      reasons: {
        abuse: 'إساءة أو مضايقة',
        spam: 'محتوى مزعج أو إعلاني',
        false_religious_claim: 'نسبة قول ديني إلى غير قائله',
        unauthorised_photo: 'صورة منشورة دون إذن',
        wrong_place: 'المكان غير صحيح',
        private_information: 'الموقع أو الصورة يكشفان معلومات خاصة',
        other: 'مخالفة أخرى',
      },
      details: 'تفاصيل تساعد المشرف (اختياري)',
      send: 'أرسل البلاغ',
      sending: 'أرسل…',
      sent: 'وصل بلاغك، وسيراجعه مشرف.',
      signIn: 'ادخل لتبلّغ.',
      verify: 'أكّد بريدك لتبلّغ.',
    },
    block: {
      action: 'احجب',
      unblock: 'ألغِ الحجب',
      title: (name: string) => `حجب ${name}؟`,
      lead: 'لن يرى أحدكما الآخر في تواصل: لا منشوراته ولا تعليقاته ولا صفحته، وتنتهي المتابعة بينكما. تلغي الحجب متى شئت من «ملفي».',
      confirm: 'احجب',
      cancel: 'تراجع',
      blocking: 'أحجب…',
      blocked: 'حجبت هذا العضو. لم يعد يراك ولا تراه في تواصل.',
      unblocked: 'ألغيت الحجب.',
      listTitle: 'المحجوبون',
      listHint: 'من حجبتهم لا يرونك ولا تراهم في تواصل. أنت وحدك ترى هذه القائمة.',
      listEmpty: 'لم تحجب أحدًا.',
      listLoading: 'نحمّل القائمة…',
      listFailed: 'تعذّر تحميل قائمة المحجوبين.',
      signIn: 'ادخل لتحجب عضوًا.',
    },
    profile: {
      joined: (month: string) => `انضم في ${month}`,
      counts: { posts: 'منشورات', followers: 'متابعون', following: 'يتابع' },
      follow: 'تابع',
      following: 'تتابعه',
      unfollow: 'ألغِ المتابعة',
      you: 'هذه صفحتك العامة.',
      signIn: 'ادخل لتتابع',
      verify: 'أكّد بريدك لتتابع.',
      loading: 'نحمّل الصفحة…',
      notFound: {
        title: 'لم نجد هذا العضو',
        description: 'ربما تغيّر المعرّف أو لم يوجد أصلًا.',
      },
      failed: 'تعذّر تحميل الصفحة الآن.',
      posts: 'بصائر منشورة',
      noPosts: 'لم ينشر بصيرة بعد.',
      edit: 'عدّل هويتك العامة',
    },
    identity: {
      title: 'هويتك العامة',
      description:
        'الاسم والمعرّف اللذان يظهران للناس في تواصل. لا يُستعمل اسم حسابك ولا بريدك أبدًا، وتختارهما مرة ثم تغيّرهما متى شئت.',
      handle: 'المعرّف',
      handleHint:
        'من 3 إلى 30 حرفًا: حروف عربية أو لاتينية وأرقام وشرطة سفلية، يبدأ بحرف. صفحتك تكون /u/المعرّف.',
      name: 'الاسم العام',
      nameHint: 'من حرف إلى 40 حرفًا، بلا رابط ولا بريد.',
      save: 'احفظ هويتي',
      saving: 'أحفظ…',
      saved: 'حُفظت هويتك العامة.',
      page: 'صفحتك العامة',
      none: 'لم تختر هوية عامة بعد. تحتاجها قبل أن تنشر أو تعلّق.',
      verify: 'أكّد بريدك أولًا لتختار هوية عامة.',
      signIn: 'ادخل لتختار هويتك العامة.',
      taken: 'هذا المعرّف يحمله عضو آخر. اختر غيره.',
      problems: {
        handleMissing: 'اكتب معرّفًا.',
        handleShape: 'المعرّف يبدأ بحرف، ويحوي حروفًا وأرقامًا وشرطة سفلية فقط، من 3 إلى 30 حرفًا.',
        handleReserved: 'هذا المعرّف محجوز للمنصة.',
        nameMissing: 'اكتب اسمًا عامًا.',
        nameLong: 'الاسم العام 40 حرفًا على الأكثر.',
        nameInvalid: 'الاسم العام بلا رابط ولا بريد ولا رموز مخفية.',
      },
    },
    publish: {
      title: 'انشر بصيرة في تواصل',
      lead: 'تُنشر البصيرة كما تحقّقت تبصرة منها: عنوانها ولمحتها والآية والحديث بمرجعيهما. تضيف إليها كلماتك إن شئت، وتظهر موسومة بأنها كلماتك.',
      noInsight: {
        title: 'اختر بصيرة أولًا',
        description: 'يبدأ النشر من بصيرة محفوظة في عالمك: افتحها واختر «انشر في تواصل».',
        world: 'افتح عالمي',
      },
      signIn: 'ادخل لتنشر بصيرتك.',
      verify: 'أكّد بريدك قبل أن تنشر شيئًا للناس.',
      identityFirst: 'اختر هويتك العامة قبل أن تنشر.',
      reflection: 'كلماتك (اختياري)',
      reflectionHint: (max: number) =>
        `ما الذي علّمتك هذه البصيرة؟ ${max} حرفًا على الأكثر. تظهر كلماتك موسومة بأنها كلماتك، لا نصًا موثّقًا.`,
      visibility: 'من يرى المنشور؟',
      visibilityHint: 'المتابعة لا تحتاج قبولًا، فـ«للمتابعين» تعني كل من يتابعك.',
      createDraft: 'أنشئ المسودة',
      creating: 'أنشئ المسودة…',
      drafted: 'أُنشئت المسودة. لا يراها أحد غيرك حتى تنشرها.',
      preview: 'هكذا يظهر منشورك',
      submit: 'انشر',
      submitting: 'أنشر…',
      edit: 'عدّل المسودة',
      saveEdit: 'احفظ التعديل',
      saving: 'أحفظ…',
      edited: 'حُفظ التعديل.',
      cancelEdit: 'تراجع',
      withdraw: 'اسحب المنشور',
      withdrawDraft: 'احذف المسودة',
      withdrawTitle: 'سحب المنشور؟',
      withdrawLead:
        'يُمحى المنشور وكلماتك وتعليقاته وآثاره من تواصل في الحال، ويبقى رابطه يقول إنه سُحب. تبقى البصيرة في عالمك.',
      withdrawConfirm: 'اسحب',
      withdrawing: 'أسحب…',
      withdrawn: 'سُحب المنشور من تواصل.',
      notPublishable: 'لا يمكن نشر هذه البصيرة: تُنشر البصائر المتحقَّقة التي تملكها وحدها.',
      unavailable: 'النشر غير متاح الآن. أعد المحاولة بعد قليل.',
      photo: 'أرفق الصورة',
      photoHint:
        'تصير صورة مشهدك عامة مع المنشور لكل من يفتحه، وتُحذف نسختها العامة حين تسحبه. لا تُعرض مع منشور للمتابعين فقط.',
      outcome: {
        published: 'نُشرت بصيرتك في تواصل.',
        pending_review: 'وصلت بصيرتك، ويراجعها مشرف قبل أن يراها الناس.',
        rejected: 'لم تُنشر. عدّل كلماتك ثم أعد الإرسال إن شئت.',
      },
      open: 'افتح المنشور',
    },
    gone: {
      title: 'سُحب هذا المنشور',
      description: 'سحبه صاحبه أو أزاله مشرف، فلم يبق منه إلا هذا العنوان.',
    },
    notFound: {
      title: 'لم نجد هذا المنشور',
      description: 'ربما لم يُنشر بعد، أو لا يُعرض لك.',
    },
    back: 'العودة إلى تواصل',
  },

  footer: {
    label: 'روابط الموقع',
    terms: 'شروط الاستخدام',
    privacy: 'سياسة الخصوصية',
    support: 'الدعم',
    cookieSettings: 'إعدادات ملفات تعريف الارتباط',
  },

  /** The world and practice states on sample data (/dev/world). Never part of a production build. */
  devWorld: {
    title: 'عالمي وتمرينك على بيانات تجريبية',
    description: 'حالات الشاشتين في المظهرين: نصوصها بين أقواس لأنها ليست من الخادم.',
    states: {
      world: 'عالم فيه موضعان وخيط',
      opened: 'موضع مفتوح',
      newcomer: 'عالم ضيف جديد تحت الضباب',
      practice: 'تمرينك',
      practiceEmpty: 'تمرينك لضيف جديد',
    },
  },

  /** The development gallery (/dev/ui). Never part of a production build. */
  dev: {
    title: 'معرض المكوّنات',
    description: 'كل مكوّن في المظهرين جنبًا إلى جنب. صفحة للتطوير، لا تُبنى في الإنتاج.',
    themes: { light: 'المظهر الفاتح', dark: 'المظهر الداكن' },
    frames: {
      shell: 'الهيكل وإطار المشهد في المقاسات الثلاثة',
      insight: 'إطار البصيرة',
      layouts: 'قوالب التخطيط',
      components: 'المكوّنات في المظهرين',
    },
    viewports: { phone: 'هاتف · ٣٧٥', tablet: 'لوحي · ٨٣٤', desktop: 'حاسوب · ١٤٤٠' },
    layouts: {
      map: 'خريطة وقائمة جانبية (عالمي، الأطلس)',
      feed: 'عمود المنشورات وعمود جانبي (تواصل)',
      settings: 'أقسام الإعدادات (ملفي)',
    },
    sections: {
      buttons: 'الأزرار',
      chips: 'الوسوم',
      glass: 'اللوح الزجاجي',
      theme: 'مبدّل المظهر',
      sheet: 'اللوح السفلي',
      scene: 'الصورة ونقاط البصائر',
      evidence: 'بطاقتا الدليل',
      progress: 'مراحل الإعداد',
      step: 'الخطوة الصغيرة',
      disclosure: 'سطر الإفصاح',
      brand: 'العلامة وزر المظهر',
      motion: 'مبدّل الحركة',
      starter: 'بدء مشهد جديد',
      list: 'قائمة البصائر',
      done: 'زر «تمّ»',
      fields: 'الحقول والرسائل والاختيارات',
      invitation: 'دعوة حفظ المسار',
      questions: 'أسئلة الملف الاختيارية',
    },
    samples: {
      primary: 'تمّ',
      secondary: 'افتح المصدر',
      ghost: 'سأفعله لاحقًا',
      disabled: 'غير متاح',
      share: 'شارك البصيرة',
      openSheet: 'افتح اللوح',
      sheetTitle: 'لماذا ظهر هذا؟',
      sheetBody: '[سبب الربط وحدوده يأتيان من الخادم]',
      glassTitle: 'ما ظهر في الصورة',
      glassBody: '[وصف ما ظهر في الصورة يأتي من الخادم]',
      chipRelation: 'صلة مباشرة',
      stepBody: '[الخطوة تأتي من المسار المعتمد]',
      stepConfirm: '[فعل الإقرار يأتي مع الخطوة]',
      selected: 'اخترت:',
      none: 'لم تختر بعد',
      reset: 'أعد الضبط',
      next: 'المرحلة التالية',
      slow: 'انتظار طويل',
      scenePlaceholderAlt: 'صورة بديلة للتطوير: سماء ليلية وأرض، بلا مشهد حقيقي',
      picked: 'وصل ملف:',
      nothingYet: 'لم يصل شيء بعد',
      fieldLabel: '[اسم الحقل]',
      fieldHint: '[قاعدة الحقل]',
      fieldError: '[سبب الرفض]',
      notice: '[رسالة عمّا حدث]',
      switchLabel: '[خيار]',
      switchHint: '[ما يفعله الخيار]',
      choiceLegend: '[سؤال]',
      choices: ['[جواب أول]', '[جواب ثان]', '[جواب ثالث]'],
      guest: 'اختار الضيف أن يتابع',
    },
    points: [
      { title: '[عنوان البصيرة الأولى]', glimpse: '[لمحة من الخادم]' },
      { title: '[عنوان البصيرة الثانية]', glimpse: '[لمحة من الخادم]' },
    ],
    placeholders: {
      quranText: '[نص الآية يأتي من المدونة]',
      quranReference: '[السورة · رقم الآية]',
      hadithChain: '[سند الحديث يأتي من المدونة]، ',
      hadithBody: '[متن الحديث يأتي من المدونة] ',
      hadithWords: '[كلمات النبي ﷺ تأتي من المدونة]',
      hadithTail: ' [تعليق المحدّث يأتي من المدونة]',
      hadithReference: '[الكتاب · رقم الحديث]',
      ruling: '[يسجّله محرّر من الدرر قبل العرض]',
      explanation: '[شرح تبصرة يأتي من الخادم بعد التحقق]',
      map: '[الخريطة]',
      mapPanel: '[قائمة الأماكن]',
      feed: '[المنشورات]',
      feedAside: '[التبويبان والمرشحات]',
      settingsNav: '[أقسام ملفي]',
      settingsBody: '[الإعداد المختار]',
    },
  },

  ...scanMessages,
  ...shareMessages,
} as const;

export type Messages = typeof ar;
