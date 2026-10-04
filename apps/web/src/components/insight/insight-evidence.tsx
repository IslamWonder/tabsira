import { Notice } from '@/components/ui/notice';
import type { Insight } from '@/lib/scan/api';
import { spansInUtf16 } from '@/lib/scan/spans';
import { messages } from '@/messages';
import { EvidenceCard } from './evidence-card';
import { EvidencePair } from './evidence-pair';

/** Below this many characters each, the two texts may sit side by side on a wide screen (tajriba §6). */
const SHORT_TEXT = 280;

/** The fields both the owner's insight and the public one carry. */
export type EvidenceSource = Pick<Insight, 'quran' | 'hadith' | 'hadith_status' | 'notice'>;

/**
 * The verse and the hadith of an insight, exactly as the API returns them:
 * the stored text is passed through untouched (never trimmed, joined,
 * shortened or normalised), with the reference, the source link, the ruling
 * and the the dorar verification link the API gives. A verse whose hadith still waits
 * for its ruling stands alone, with the API's notice beside it, so the reader
 * is told why and never shown a hadith that has not been ruled on.
 */
export function InsightEvidence({ insight }: { insight: EvidenceSource }) {
  const { quran, hadith } = insight;
  const verse = quran?.verse;
  const narration = hadith?.hadith;
  const ruling = narration?.ruling ?? null;

  const quranCard =
    verse === undefined ? undefined : (
      <EvidenceCard
        variant="quran"
        text={verse.text}
        reference={messages.insightPage.verseReference(verse.surah_name, verse.ayah)}
        sourceHref={verse.links.quranpedia}
        verified={verse.status === 'verified_cached'}
      />
    );
  const sunnahCard =
    narration === undefined ? undefined : (
      <EvidenceCard
        variant="sunnah"
        text={narration.text}
        spans={spansInUtf16(narration.text, narration.spans)}
        reference={messages.insightPage.hadithReference(
          narration.collection.name_ar,
          narration.number
        )}
        // The page of the ruling when an editor recorded one; otherwise the search the reader runs.
        sourceHref={ruling?.dorar_url ?? narration.links.dorar_verification}
        verifyHref={narration.links.dorar_verification}
        ruling={ruling?.ruling_text}
        rulingSource={
          ruling === null
            ? undefined
            : messages.insightPage.rulingSource(ruling.scholar, ruling.source_book, ruling.page)
        }
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
      {insight.hadith_status === 'awaiting_verification' && insight.notice !== null ? (
        <div role="status">
          <Notice tone="info">{insight.notice}</Notice>
        </div>
      ) : null}
    </div>
  );
}
