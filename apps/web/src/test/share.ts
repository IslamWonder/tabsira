import type { PublicInsight } from '@/lib/share-card/layout';
import { insightOut, sha256 } from './scan';

/**
 * A published insight as GET /public/insights/{id} returns it, built from the
 * stand-in scripture of the insight fixture (never a real verse or hadith).
 */
export function publicInsightOut(overrides: Partial<PublicInsight> = {}): PublicInsight {
  const insight = insightOut();
  return {
    id: insight.id,
    engine: insight.engine,
    label: insight.label,
    title: insight.title,
    glimpse: insight.glimpse,
    relation: insight.relation,
    relation_label: insight.relation_label,
    // The public schemas carry the text and its tag, never why the engine chose it.
    quran: insight.quran === null ? null : { tag: insight.quran.tag, verse: insight.quran.verse },
    hadith:
      insight.hadith === null ? null : { tag: insight.hadith.tag, hadith: insight.hadith.hadith },
    hadith_status: insight.hadith_status,
    pair_complete: insight.pair_complete,
    explanation_tag: insight.explanation_tag,
    explanation: insight.explanation.filter((part) => part.section !== 'seen'),
    small_step: insight.small_step,
    author: null,
    published_at: '2026-10-04T09:00:00Z',
    disclosure: insight.disclosure,
    ...overrides,
  };
}

/** The same insight with the verse and the hadith lengthened by repeating the stored text. */
export function withLongScripture(
  insight: PublicInsight,
  verseTimes: number,
  hadithTimes: number
): PublicInsight {
  const { quran, hadith } = insight;
  if (quran === null || hadith === null) {
    throw new Error('the fixture needs both a verse and a hadith');
  }
  const verseText = Array(verseTimes).fill(quran.verse.text).join('');
  const hadithText = Array(hadithTimes).fill(hadith.hadith.text).join(' ');
  // The hash follows the lengthened text, so it still says what the stored text hashes to.
  return {
    ...insight,
    quran: { ...quran, verse: { ...quran.verse, text: verseText, sha256: sha256(verseText) } },
    hadith: {
      ...hadith,
      hadith: { ...hadith.hadith, text: hadithText, sha256: sha256(hadithText) },
    },
  };
}
