import type { Insight } from '@/lib/scan/api';
import { spansInUtf16 } from '@/lib/scan/spans';
import { messages } from '@/messages';
import { EvidenceCard } from './evidence-card';
import { EvidencePair } from './evidence-pair';

/** Below this many characters each, the two texts may sit side by side on a wide screen (tajriba §6). */
const SHORT_TEXT = 280;

/** The fields both the owner's insight and the public one carry. */
export interface EvidenceSource {
  quran: Pick<NonNullable<Insight['quran']>, 'verse'> | null;
  hadith: Pick<NonNullable<Insight['hadith']>, 'hadith'> | null;
  hadith_status: Insight['hadith_status'];
}

/**
 * The verse and the hadith of an insight, exactly as the API returns them:
 * the stored text is passed through untouched (never trimmed, joined,
 * shortened or normalised), with its reference. No ruling is shown (decision 64).
 */
export function InsightEvidence({
  insight,
  headingLevel,
}: {
  insight: EvidenceSource;
  /** Level of each card's heading; 3 when the texts sit under a heading of their own, as in the chat sheet. */
  headingLevel?: 2 | 3;
}) {
  const { quran, hadith } = insight;
  const verse = quran?.verse;
  const narration = hadith?.hadith;

  const quranCard =
    verse === undefined ? undefined : (
      <EvidenceCard
        variant="quran"
        headingLevel={headingLevel}
        text={verse.text}
        reference={messages.insightPage.verseReference(verse.surah_name, verse.ayah)}
        verified={verse.status === 'verified_cached'}
      />
    );
  const sunnahCard =
    narration === undefined ? undefined : (
      <EvidenceCard
        variant="sunnah"
        headingLevel={headingLevel}
        text={narration.text}
        spans={spansInUtf16(narration.text, narration.spans)}
        reference={messages.insightPage.hadithReference(
          narration.collection.name_ar,
          narration.number
        )}
      />
    );
  const short =
    verse !== undefined &&
    narration !== undefined &&
    verse.text.length < SHORT_TEXT &&
    narration.text.length < SHORT_TEXT;

  return (
    <div className="flex flex-col gap-3">
      <EvidencePair quran={quranCard} sunnah={sunnahCard} sideBySide={short} />
    </div>
  );
}
