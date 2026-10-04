// Sample answers of the social API for the screenshots: a few posts in both
// feeds, one post with its comments, one profile. Placeholders stand where the
// API would put scripture; nothing here is ever shown as live data.

const AUTHOR = { handle: 'rain_reader', public_name: 'قارئ المطر' };
const OTHER = { handle: 'noor_f', public_name: 'نور' };
const ME = { handle: 'reader', public_name: 'قارئ تبصرة' };

const QURAN = {
  surah: 30,
  ayah: 50,
  surah_name: '[اسم السورة]',
  text: '[نص الآية يأتي من المدونة كما هو، حرفًا حرفًا]',
  sha256: '0'.repeat(64),
  source_url: 'https://quranpedia.net/',
  verified: true,
};

const HADITH = {
  collection: 'bukhari',
  collection_name: '[اسم الكتاب]',
  number: '1032',
  text: '[نص الحديث يأتي من المدونة كما هو، بسنده ومتنه]',
  sha256: '0'.repeat(64),
  classification: 'صحيح',
  verification_url: 'https://dorar.net/',
  verified: true,
};

function post(id, author, title, glimpse, extra = {}) {
  return {
    id,
    author,
    insight: {
      title,
      glimpse,
      relation_type: 'direct',
      concepts: ['rain'],
      explanation:
        '[شرح تبصرة يأتي من الخادم بعد التحقق: وجه الصلة بين المشهد والنصين، في سطرين أو ثلاثة.]',
      step: '[خطوة صغيرة من المسار المعتمد]',
      has_photo: false,
      insight_version: 1,
      quran: [QURAN],
      hadith: [HADITH],
    },
    reflection: null,
    visibility: 'public',
    status: 'published',
    status_reason: null,
    status_message: null,
    published_at: '2026-10-04T10:00:00Z',
    created_at: '2026-10-04T09:50:00Z',
    like_count: 3,
    comment_count: 2,
    viewer: null,
    why: null,
    ...extra,
  };
}

export const POST_ID = '7345678901234567890';

const FIRST = post(
  POST_ID,
  AUTHOR,
  'الحياة في قطرة',
  'الماء سبب للحياة، وقطرة واحدة تذكّر بأن النماء يبدأ صغيرًا.',
  {
    reflection: {
      text: 'رأيت المطر على ورقة نبتة صغيرة في شرفتنا، فتذكّرت كم من حياةٍ تبدأ بقطرة.',
      source: 'user',
      verified: false,
      looks_like_scripture: false,
    },
    why: { code: 'fresh', text: 'بصيرة نُشرت قبل قليل' },
  }
);
const SECOND = post(
  '7345678901234567891',
  OTHER,
  'الغرس الذي يتعدّاك',
  'ما تغرسه اليوم ينتفع به من لا تعرفه.',
  {
    why: { code: 'new_topic', text: 'لتنويع ما تقرؤه: موضوع مختلف عمّا قبله' },
    like_count: 0,
    comment_count: 0,
  }
);
// The second post's hadith awaits its ruling: the verse stands alone.
SECOND.insight = { ...SECOND.insight, hadith: [] };

function viewerOf(state, authorHandle) {
  return state === 'signed-in'
    ? { liked: false, bookmarked: false, is_author: authorHandle === ME.handle }
    : null;
}

function withViewer(item, state) {
  return { ...item, viewer: viewerOf(state, item.author.handle) };
}

const COMMENTS = [
  {
    id: '7345678901234567900',
    author: OTHER,
    body: 'جميلة. الدعاء الوارد في الحديث أردّده كل مطر.',
    created_at: '2026-10-04T10:20:00Z',
    status: 'published',
    status_message: null,
    is_mine: false,
    replies: [
      {
        id: '7345678901234567901',
        author: AUTHOR,
        body: 'وأنا كذلك، منذ هذه البصيرة.',
        created_at: '2026-10-04T10:25:00Z',
        status: 'published',
        status_message: null,
        is_mine: false,
        replies: [],
      },
    ],
  },
];

/** The sample answer of a social route, or undefined when the route is not one. */
export function socialAnswer(method, pathname, state) {
  const route = `${method} ${pathname}`;
  if (route === 'GET /feed/for-you' || route === 'GET /feed/latest') {
    const items = [FIRST, SECOND].map((item) => withViewer(item, state));
    return {
      items: route.endsWith('latest') ? items.map((item) => ({ ...item, why: null })) : items,
      next_cursor: null,
      empty_reason: null,
    };
  }
  if (route === 'GET /feed/following') {
    return { items: [withViewer(FIRST, state)], next_cursor: null, empty_reason: null };
  }
  if (route === 'GET /me/posts') {
    const mine = post('7345678901234567895', ME, 'ظلّ يمتد', 'الظل يتبع النور ولا يسبقه.', {
      status: 'pending_review',
      status_message: 'يحتاج إلى مراجعة مشرف قبل نشره.',
      published_at: null,
      viewer: { liked: false, bookmarked: false, is_author: true },
    });
    return { items: [mine], next_cursor: null };
  }
  if (route === 'GET /me/bookmarks') {
    return { items: [], next_cursor: null, empty_reason: 'no_posts' };
  }
  if (route === 'GET /me/public-identity') {
    return state === 'signed-in' ? ME : null;
  }
  if (route === 'GET /blocks') {
    return [];
  }
  if (route === `GET /posts/${POST_ID}`) {
    return withViewer({ ...FIRST, why: null }, state);
  }
  if (route === `GET /posts/${POST_ID}/comments`) {
    return { items: COMMENTS, next_cursor: null };
  }
  if (route === `GET /u/${AUTHOR.handle}`) {
    return {
      ...AUTHOR,
      joined_month: '2026-09',
      posts_count: 4,
      followers_count: 12,
      following_count: 7,
      viewer: state === 'signed-in' ? { follows: true, is_self: false } : null,
    };
  }
  if (route === `GET /u/${AUTHOR.handle}/posts`) {
    return {
      items: [withViewer({ ...FIRST, why: null }, state)],
      next_cursor: null,
      empty_reason: null,
    };
  }
  return undefined;
}

export const PROFILE_HANDLE = AUTHOR.handle;
