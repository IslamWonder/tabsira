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
      practice: {
        body: 'هنا ستظهر مراتب التمرين والسلسلة وعلامات المواظبة حين تُبنى.',
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
          terms: 'الشروط والخصوصية',
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
      opening: 'تُفتح هنا البصيرة كاملة: الآية والحديث من مصدرهما الموثّق، ووجه الصلة، وخطوة صغيرة.',
      pending: 'نربط هذا المشهد بالخادم قريبًا؛ لا نعرض نصًا قبل أن يأتي من مصدره.',
    },
    received: {
      photoTitle: 'صورتك',
      linkTitle: 'رابط صورتك',
      note: 'لم يُرسَل شيء إلى أي مكان. التحليل الحي قيد الإعداد، وستُحلَّل الصورة هنا حين يُفعَّل.',
      photoAlt: 'الصورة التي اخترتها',
    },
    starter: {
      prompt: 'أو ابدأ بمشهدك: اسحب صورة إلى هنا',
      dropping: 'أفلت الصورة هنا',
      choose: 'اختر صورة',
      camera: 'التقط بالكاميرا',
      pasteLink: 'الصق رابط صورة',
      linkLabel: 'رابط الصورة',
      useLink: 'استخدم الرابط',
      invalidLink: 'هذا لا يبدو رابطًا. انسخ عنوان الصورة كاملًا ثم أعد المحاولة.',
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

  victory: {
    title: 'اكتُشِف المعنى',
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
    complete: 'بصيرتك جاهزة',
    slow: 'ما زلنا نعمل على طلبك، وقد يستغرق وقتًا أطول من المعتاد.',
    cancel: 'ألغِ',
  },

  step: {
    title: 'خطوة صغيرة',
    defer: 'أجّل الآن',
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

  footer: {
    label: 'روابط الموقع',
    terms: 'شروط الاستخدام',
    privacy: 'سياسة الخصوصية',
    support: 'الدعم',
    cookieSettings: 'إعدادات ملفات تعريف الارتباط',
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
      ghost: 'أجّل الآن',
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
      linked: 'وصل رابط:',
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
} as const;

export type Messages = typeof ar;
