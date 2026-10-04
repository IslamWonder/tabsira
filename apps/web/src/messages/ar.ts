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

  brand: {
    wordmark: 'تَبْصِرَة',
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
        appearance: 'المظهر',
        motion: 'الحركة',
        account: 'الحساب والخصوصية',
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
