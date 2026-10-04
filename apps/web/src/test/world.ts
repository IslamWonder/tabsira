import type { Progress } from '@/progress/api';
import type { Place, Region, Relation, Treasure, World } from '@/world/api';

/*
 * Sample answers of the world and practice routes, in the shapes the API
 * publishes, for unit tests and the /dev/ui gallery. Texts are bracketed
 * placeholders: no scripture is typed by hand anywhere in the web code, and
 * the tests compare what is shown with what the "API" returned, byte for byte.
 */

const region = (
  id: string,
  name: string,
  x: number,
  y: number,
  placeId: string | null
): Region => ({
  id,
  domain_id: id,
  name,
  domain_title: `[مجال ${id}]`,
  position: { x, y },
  fog: placeId === null,
  place_id: placeId,
});

export const REGIONS: Region[] = [
  region('T00', '[منطقة أولى]', 0.5, 0.9, '7001'),
  region('T01', '[منطقة ثانية]', 0.3, 0.78, '7002'),
  region('T02', '[منطقة ثالثة]', 0.5, 0.08, null),
  region('T03', '[منطقة رابعة]', 0.28, 0.16, null),
];

export const PLACE_ONE: Place = {
  id: '7001',
  region_id: 'T00',
  name: '[موضع أول]',
  created_at: '2026-10-01T08:00:00Z',
  last_visited_at: '2026-10-03T08:00:00Z',
  insights: [{ id: '9001', title: '[بصيرة أولى]', completed_at: '2026-10-01T08:00:00Z' }],
  treasure: null,
};

export const PLACE_TWO: Place = {
  id: '7002',
  region_id: 'T01',
  name: '[موضع ثان]',
  created_at: '2026-10-02T08:00:00Z',
  last_visited_at: null,
  insights: [
    { id: '9002', title: '[بصيرة ثانية]', completed_at: '2026-10-02T08:00:00Z' },
    { id: '9003', title: '[بصيرة ثالثة]', completed_at: '2026-10-02T09:00:00Z' },
  ],
  treasure: { id: '8001' },
};

export const RELATION: Relation = {
  place_a_id: '7001',
  place_b_id: '7002',
  reason: 'same_scene',
  reason_label: '[سبب الصلة]',
  question: '[كيف ترتبطان؟]',
  insight_ids: ['9001', '9002', '9999'],
};

export const WORLD: World = {
  version: '1.0',
  path_version: 'tabsira-masar-1.0',
  regions: REGIONS,
  places: [PLACE_ONE, PLACE_TWO],
  relations: [RELATION],
};

/** A newcomer: the whole map under fog. */
export const WORLD_UNDER_FOG: World = {
  ...WORLD,
  regions: REGIONS.map((item) => ({ ...item, fog: true, place_id: null })),
  places: [],
  relations: [],
};

export const QURAN_TEXT = '[نص الآية يأتي من الخادم]';
export const HADITH_TEXT = '[سند]، [متن] [كلمات النبي] [تعليق]';
// SHA-256 of the two texts above (UTF-8), computed once; a test recomputes them and compares.
export const QURAN_SHA256 = 'eb2e9fff5afe3d0f9a14654fc59fdf58f335e9d52ba8af10286e1bd3bc68a4c3';
export const HADITH_SHA256 = 'dd0cca10816aa7215d1b56350cd0c8ffcb023fd5f85ca03024406c360470b4fc';

export const TREASURE: Treasure = {
  id: '8001',
  kind: 'alternative',
  kind_label: '[نوع الكنز]',
  insight_id: '9002',
  place_id: '7002',
  quran: {
    tag: 'quran',
    why: null,
    verse: {
      surah: 30,
      ayah: 50,
      surah_name: '[اسم السورة]',
      text: QURAN_TEXT,
      sha256: QURAN_SHA256,
      page: 1,
      juz: 1,
      source: {
        name: 'quranpedia.net',
        url: 'https://quranpedia.net/example',
        mushaf_id: 2,
        mushaf_name: '[مصحف]',
        quranpedia_ayah_id: 1,
        version: '1',
        dump_version: null,
        last_sync_at: null,
      },
      links: { quranpedia: 'https://quranpedia.net/example/30/50' },
      status: 'verified_cached',
    },
  },
  hadith: {
    tag: 'hadith',
    why: null,
    hadith: {
      collection: {
        slug: 'bukhari',
        name_ar: '[اسم الكتاب]',
        source_dataset: 'fawazahmed0',
        source_url: 'https://example.org/hadith',
        licence: 'Unlicense',
        version: '1',
      },
      number: '1032',
      arabic_number: '[١٠٣٢]',
      chapter: null,
      text: HADITH_TEXT,
      sha256: HADITH_SHA256,
      spans: [{ start: 0, end: 5, role: 'chain' }],
      informational_grades: null,
      ruling: {
        ruling_text: '[نص الحكم]',
        scholar: '[عالم]',
        source_book: '[كتاب]',
        page: '1',
        dorar_url: 'https://dorar.net/example',
        classification: 'صحيح',
        recorded_at: '2026-10-01T08:00:00Z',
      },
      eligible: true,
      links: { dorar_verification: 'https://dorar.net/verify/1' },
      status: 'local_corpus',
    },
  },
  learning_unit: { id: 'U01', title: '[وحدة من المسار]' },
  revealed_at: null,
  disclosure: '[إفصاح الكنز]',
};

export const PROGRESS: Progress = {
  timezone: 'UTC',
  rank: {
    id: 'mutaammil',
    title: '[مرتبة]',
    hint: '[تلميح المرتبة]',
    looks: 4,
    next: { id: 'mustabsir', title: '[المرتبة التالية]', minimum: 10 },
    progress: 0.25,
  },
  streak: {
    current: 3,
    best: 5,
    last_day: '2026-10-04',
    days: [
      { day: '2026-10-04', looked: true },
      { day: '2026-10-03', looked: true },
      { day: '2026-10-02', looked: true },
      { day: '2026-10-01', looked: false },
      { day: '2026-09-30', looked: false },
      { day: '2026-09-29', looked: true },
      { day: '2026-09-28', looked: false },
    ],
  },
  daily_quest: {
    title: '[مهمة اليوم]',
    day: '2026-10-04',
    steps: [
      { id: 'look', label: '[خطوة النظر]', done: true },
      { id: 'complete', label: '[خطوة الإتمام]', done: false },
    ],
    done: false,
    days_done: 2,
  },
  sky: {
    count: 2,
    stars: [
      { concept: '[معنى أول]', count: 1, first_seen: '2026-10-01T08:00:00Z', x: 0.2, y: 0.3 },
      { concept: '[معنى ثان]', count: 4, first_seen: '2026-10-02T08:00:00Z', x: 0.7, y: 0.6 },
    ],
  },
  badges: [
    {
      id: 'first-look',
      title: '[علامة نالها]',
      description: '[وصف علامة]',
      earned: true,
      earned_at: '2026-10-01T08:00:00Z',
    },
    {
      id: 'seven-looks',
      title: '[علامة مقفلة]',
      description: '[وصف علامة مقفلة]',
      earned: false,
      earned_at: null,
    },
  ],
  counts: { looks: 4, completed: 3, actions_done: 1, places: 2, treasures: 0, questions: 5 },
  disclaimer: '[تنبيه التمرين]',
};

/** A learner at the top rank with everything done: the other branch of each condition. */
export const PROGRESS_COMPLETE: Progress = {
  ...PROGRESS,
  rank: { ...PROGRESS.rank, next: null, progress: 1 },
  daily_quest: {
    ...PROGRESS.daily_quest,
    done: true,
    steps: PROGRESS.daily_quest.steps.map((step) => ({ ...step, done: true })),
  },
};

/** A newcomer: nothing recorded yet. */
export const PROGRESS_EMPTY: Progress = {
  ...PROGRESS,
  rank: { ...PROGRESS.rank, looks: 0, progress: 0 },
  streak: {
    current: 1,
    best: 1,
    last_day: null,
    days: PROGRESS.streak.days.map((day) => ({ ...day, looked: false })),
  },
  sky: { count: 0, stars: [] },
  badges: PROGRESS.badges.map((badge) => ({ ...badge, earned: false, earned_at: null })),
  counts: { looks: 0, completed: 0, actions_done: 0, places: 0, treasures: 0, questions: 0 },
};
