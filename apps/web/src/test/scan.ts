import { createHash } from 'node:crypto';
import type { ChatReply, Completion, Insight, Progress, Scan, Tutorial } from '@/lib/scan/api';

/*
 * Sample answers of the scan, insight and tutorial routes, in the shapes the
 * API publishes, for unit tests only. The scripture below is a stand-in that
 * carries the awkward bytes a real text may carry (a direction mark, a double
 * space, a trailing space, a Uthmani mark written as an escape); it is never a
 * real verse or hadith, and a test that renders it compares it byte for byte.
 */

/** A stand-in verse with an escape for a Uthmani mark: the source file never holds one raw. */
export const VERSE_TEXT = `[آية للاختبار]\u0670  بين فراغين \u200F `;
/** The SHA-256 the API stores beside a text: of its UTF-8 bytes. */
export const sha256 = (text: string) => createHash('sha256').update(text, 'utf8').digest('hex');

export const HADITH_TEXT = '[حديث للاختبار] سند الرواية: قال النبي: [كلام للاختبار] ختام.';
const WORDS_AT = HADITH_TEXT.indexOf('قال');
const TAIL_AT = HADITH_TEXT.indexOf(' ختام');
/** Offsets of the chain, the words and the closing in HADITH_TEXT (all in the Basic Multilingual Plane). */
export const HADITH_SPANS = [
  { start: 0, end: WORDS_AT, role: 'chain' as const },
  { start: WORDS_AT, end: TAIL_AT, role: 'words' as const },
  { start: TAIL_AT, end: HADITH_TEXT.length, role: 'tail' as const },
];

export function scanOut(overrides: Partial<Scan> = {}): Scan {
  return {
    id: '110000000000000001',
    status: 'done',
    outcome: 'insights',
    error_code: null,
    run: 1,
    engine: 'pipeline',
    engine_label: null,
    source: 'upload',
    sensitive: false,
    image: {
      available: true,
      width: 800,
      height: 600,
      url: '/scans/110000000000000001/image',
    },
    description: 'نبتة صغيرة في أصيص',
    entities: [
      {
        id: 'e1',
        label_arabic: 'نبتة',
        bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 },
        origin: 'detector',
        status: 'observed',
      },
      {
        id: 'e2',
        label_arabic: 'أصيص',
        bbox: { x: 0.5, y: 0.5, width: 0.3, height: 0.3 },
        origin: 'vlm',
        status: 'inferred',
      },
      { id: 'e3', label_arabic: 'ضوء', bbox: null, origin: 'vlm', status: 'inferred' },
    ],
    clarification_question: null,
    insights: [
      {
        id: '110000000000000002',
        title: 'عنوان البصيرة الأولى',
        glimpse: 'لمحة البصيرة الأولى',
        anchor: { x: 0.1, y: 0.2, width: 0.2, height: 0.2 },
        relation: 'direct',
        relation_label: 'صلة مباشرة',
        completed: false,
      },
      {
        id: '110000000000000003',
        title: 'عنوان البصيرة الثانية',
        glimpse: 'لمحة البصيرة الثانية',
        anchor: { x: 0.6, y: 0.6, width: 0.2, height: 0.2 },
        relation: 'close_conceptual',
        relation_label: 'صلة مفهومية',
        completed: true,
      },
    ],
    awaiting_verification: 0,
    events_url: '/scans/110000000000000001/events',
    created_at: '2026-10-04T08:00:00Z',
    finished_at: '2026-10-04T08:00:09Z',
    disclosure: 'تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا',
    ...overrides,
  };
}

export function insightOut(overrides: Partial<Insight> = {}): Insight {
  return {
    id: '110000000000000002',
    scan_id: '110000000000000001',
    origin: 'scan',
    engine: 'pipeline',
    label: null,
    title: 'عنوان البصيرة الأولى',
    glimpse: 'لمحة البصيرة الأولى',
    anchor: { x: 0.1, y: 0.2, width: 0.2, height: 0.2 },
    relation: 'direct',
    relation_label: 'صلة مباشرة',
    quran: {
      tag: 'القرآن',
      verse: {
        surah: 30,
        ayah: 50,
        surah_name: 'سورة اختبار',
        text: VERSE_TEXT,
        sha256: sha256(VERSE_TEXT),
        page: 1,
        juz: 1,
        source: {
          name: 'quranpedia.net',
          url: 'https://quranpedia.net',
          mushaf_id: 2,
          mushaf_name: 'مصحف',
          quranpedia_ayah_id: 1,
          version: 'dump:1',
          dump_version: '1',
          last_sync_at: null,
        },
        links: { quranpedia: 'https://quranpedia.net/surah/30/ayah/50' },
        status: 'verified_cached',
      },
      why: { relation: 'direct', relation_label: 'صلة مباشرة', matched_on: 'أثر الماء في الأرض' },
    },
    hadith: {
      tag: 'السنة',
      hadith: {
        collection: {
          slug: 'bukhari',
          name_ar: 'صحيح اختبار',
          source_dataset: 'dataset',
          source_url: 'https://example.org/dataset',
          licence: 'Unlicense',
          version: '1',
        },
        number: '1032',
        arabic_number: null,
        chapter: null,
        text: HADITH_TEXT,
        sha256: sha256(HADITH_TEXT),
        spans: HADITH_SPANS,
        informational_grades: null,
        ruling: {
          ruling_text: 'صحيح',
          scholar: 'محدّث الاختبار',
          source_book: 'كتاب الاختبار',
          page: '12',
          dorar_url: 'https://dorar.net/hadith/sharh/1',
          classification: 'صحيح',
          recorded_at: '2026-10-01T08:00:00Z',
        },
        eligible: true,
        links: { dorar_verification: 'https://dorar.net/hadith/search?q=test' },
        status: 'local_corpus',
      },
      why: {
        relation: 'action_based',
        relation_label: 'صلة بالفعل',
        matched_on: 'رؤية المطر',
      },
    },
    hadith_status: 'shown',
    notice: null,
    pair_complete: true,
    explanation_tag: 'شرح تبصرة',
    explanation: [
      { section: 'seen', label: 'ما ظهر', text: 'نبتة صغيرة وماء.' },
      { section: 'value', label: 'القيمة', text: 'الماء نعمة.' },
      { section: 'quran', label: 'ماذا تضيف الآية', text: 'تضيف الآية معنى الإحياء.' },
      { section: 'sunnah', label: 'ماذا يضيف الحديث', text: 'يضيف الحديث دعاءً.' },
      { section: 'life', label: 'كيف يتصل بالحياة', text: 'تذكّر ذلك حين ترى المطر.' },
    ],
    why: {
      visible_clues: ['قطرات على الأوراق', 'تربة رطبة'],
      concept: 'الإحياء بالماء',
      limits: ['الصورة الواحدة لا تثبت أرضًا ميتة.'],
      personalised_because: null,
    },
    small_step: { text: 'احفظ الدعاء الوارد في الحديث.', kind: 'text_grounded', label: 'من السنة' },
    learning_unit: { id: 'T01_06', title: 'وحدة', domain_id: 'T01', path_version: 'v1' },
    action: { state: null, at: null, means: null },
    chat: { enabled: true, used: 0, limit: 3, remaining: 3, messages: [] },
    image: { sensitive: false, url: '/scans/110000000000000001/image' },
    completed_at: null,
    place_id: null,
    created_at: '2026-10-04T08:00:10Z',
    disclosure: 'تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا',
    ...overrides,
  };
}

export function completionOut(overrides: Partial<Completion> = {}): Completion {
  return {
    insight_id: '110000000000000002',
    completed_at: '2026-10-04T08:05:00Z',
    first_time: true,
    place: { id: '110000000000000009', region_id: 'T01', name: 'واحة الغيث', created: true },
    treasure_prepared: false,
    badges_earned: ['first-look'],
    options: [
      { id: 'open_world', label: 'افتح عالمي' },
      { id: 'new_scan', label: 'صوّر مشهدًا آخر' },
      { id: 'share', label: 'شارك البصيرة' },
    ],
    suggest_account: null,
    disclosure: 'تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا',
    ...overrides,
  };
}

export function chatReply(overrides: Partial<ChatReply> = {}): ChatReply {
  return {
    message: {
      question: 'ما معنى هذا؟',
      answer: 'جواب الاختبار.',
      level: 'a',
      kind: 'answer',
      answered_at: '2026-10-04T08:06:00Z',
    },
    used: 1,
    limit: 3,
    remaining: 2,
    disclosure: 'تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا',
    ...overrides,
  };
}

export function progressOut(overrides: Partial<Progress> = {}): Progress {
  return {
    timezone: 'UTC',
    rank: { id: 'nazir', title: 'ناظر', hint: 'بدأت تنظر.', looks: 1, next: null, progress: 0 },
    streak: { current: 1, best: 1, last_day: '2026-10-04', days: [] },
    daily_quest: {
      title: 'بصيرة اليوم',
      day: '2026-10-04',
      steps: [
        { id: 'look', label: 'انظر في مشهد واحد اليوم', done: true },
        { id: 'complete', label: 'أتمّ بصيرة واحدة اليوم', done: true },
      ],
      done: true,
      days_done: 1,
    },
    sky: { count: 0, stars: [] },
    badges: [
      {
        id: 'first-look',
        title: 'أول نظرة',
        description: 'أكملت أول مشهد.',
        earned: true,
        earned_at: '2026-10-04T08:05:00Z',
      },
      { id: 'asked', title: 'سائل', description: 'سألت.', earned: false, earned_at: null },
    ],
    counts: { looks: 1, completed: 1, actions_done: 0, places: 1, treasures: 0, questions: 0 },
    disclaimer: 'علامات على التمرين لا على الإيمان.',
    ...overrides,
  };
}

export function tutorialOut(): Tutorial {
  const insight = insightOut();
  return {
    scene: 'rain',
    version: '1.0',
    title: 'مطر ينزل على نبتة',
    label: 'مثال موثّق مُعدّ',
    status: 'prepared',
    image: { path: '/scene/rain-olive.jpg', width: 768, height: 1344, alt: 'نبتة تتلقى المطر' },
    insights: [
      {
        slug: 'drop',
        title: 'الحياة في قطرة',
        glimpse: 'كيف تُحيا الأرض',
        anchor: { x: 0.06, y: 0.525, width: 0.36, height: 0.06 },
        relation: 'direct',
        relation_label: 'صلة مباشرة',
        quran: insight.quran as NonNullable<Insight['quran']>,
        hadith: insight.hadith,
        hadith_status: 'shown',
        notice: null,
        pair_complete: true,
        explanation_tag: 'شرح تبصرة',
        explanation: [],
        why: insight.why,
        small_step: insight.small_step,
        learning_unit_id: 'T01_06',
      },
      {
        slug: 'planting',
        title: 'الغرس الذي يتعدّاك',
        glimpse: 'نفع يبقى',
        anchor: { x: 0.4, y: 0.6, width: 0.2, height: 0.12 },
        relation: 'direct',
        relation_label: 'صلة مباشرة',
        quran: insight.quran as NonNullable<Insight['quran']>,
        hadith: null,
        hadith_status: 'awaiting_verification',
        notice: 'الحديث بانتظار الحكم',
        pair_complete: false,
        explanation_tag: 'شرح تبصرة',
        explanation: [],
        why: insight.why,
        small_step: null,
        learning_unit_id: 'T12_02',
      },
    ],
    disclosure: 'تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا',
  };
}

/** A body of server-sent events as the API writes them (`\r\n` line ends), in chunks. */
export function sseBody(chunks: readonly string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

export function sseMessage(id: number, event: string, data: Record<string, unknown>): string {
  return `id: ${id}\r\nevent: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
}

export function sseResponse(chunks: readonly string[], status = 200): Response {
  return new Response(sseBody(chunks), {
    status,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}
