import { createHash } from 'node:crypto';
import type { Comment, MemberProfile, Post } from '@/social/types';

/*
 * Sample answers of the social API for unit tests. The scripture fields hold
 * placeholders, never a verse or a hadith (AGENTS.md); their hashes are the
 * real SHA-256 of the placeholder text, so a test can check that what the card
 * shows hashes to what the API said it sent.
 */

export function sha256(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

// Shaped so that any trim, whitespace collapse, NFC or NFKC, diacritic or tatweel
// stripping, or cut at 280 characters changes them: a display that alters the text fails.
export const QURAN_TEXT = `  [نص  الآية كما في المدونة]\u200f\u00a0مَعَ حَرَكَاتٍ وتطـــويل وآ\u0627\u0653 ${'[كلمة] '.repeat(60)}\n `;
export const HADITH_TEXT = ` [نص الحديث كما في المدونة]\t\u200f مَتْنٌ  بحركات، وتطـويل، و\u0627\u0653 ${'[كلمة] '.repeat(60)}  \n`;

export const AUTHOR = { handle: 'rain_reader', public_name: '[اسم عام]' };
export const OTHER = { handle: 'other_one', public_name: '[عضو آخر]' };

export const POST: Post = {
  id: '7345678901234567890',
  author: AUTHOR,
  insight: {
    title: '[عنوان البصيرة]',
    glimpse: '[لمحة البصيرة]',
    relation_type: 'direct',
    concepts: ['rain'],
    explanation: '[شرح تبصرة من الخادم]',
    step: '[خطوة صغيرة من الخادم]',
    has_photo: false,
    photo_url: null,
    insight_version: 1,
    quran: [
      {
        surah: 30,
        ayah: 50,
        surah_name: '[اسم السورة]',
        text: QURAN_TEXT,
        sha256: sha256(QURAN_TEXT),
        source_url: 'https://quranpedia.net/',
        verified: true,
      },
    ],
    hadith: [
      {
        collection: 'bukhari',
        collection_name: '[اسم الكتاب]',
        number: '1032',
        text: HADITH_TEXT,
        sha256: sha256(HADITH_TEXT),
        classification: 'صحيح',
        verification_url: 'https://dorar.net/',
        verified: true,
      },
    ],
  },
  reflection: {
    text: '[كلمات الكاتب]',
    source: 'user',
    verified: false,
    looks_like_scripture: false,
  },
  visibility: 'public',
  status: 'published',
  status_reason: null,
  status_message: null,
  published_at: '2026-10-04T10:00:00Z',
  created_at: '2026-10-04T09:50:00Z',
  like_count: 2,
  comment_count: 1,
  viewer: null,
  why: null,
};

/** The same post as its signed-in author sees it, with the feed's reason. */
export const MY_POST: Post = {
  ...POST,
  viewer: { liked: false, bookmarked: false, is_author: true },
};

export const COMMENT: Comment = {
  id: '7345678901234567891',
  author: OTHER,
  body: '[تعليق]',
  created_at: '2026-10-04T10:05:00Z',
  status: 'published',
  status_message: null,
  is_mine: false,
  replies: [],
};

export const PROFILE: MemberProfile = {
  handle: AUTHOR.handle,
  public_name: AUTHOR.public_name,
  joined_month: '2026-10',
  posts_count: 3,
  followers_count: 5,
  following_count: 2,
  viewer: null,
};

export const IDENTITY = { handle: 'reader', public_name: '[قارئ]' };
export const NO_IDENTITY = { handle: null, public_name: null };

export function page<T>(items: T[], next: string | null = null, emptyReason: string | null = null) {
  return { items, next_cursor: next, empty_reason: emptyReason };
}
