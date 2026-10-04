import { EvidenceCard } from '@/components/insight/evidence-card';
import { EvidencePair } from '@/components/insight/evidence-pair';
import { messages } from '@/messages';
import type { PostInsight } from '@/social/types';

const M = messages.community.post;

/**
 * The verified pair of a post, exactly as the API returned it from the
 * scripture store: the text goes to the card untouched (AGENTS.md: byte for
 * byte, never typed or changed here). A publication may cite up to three of
 * each kind; a hadith whose ruling is no longer eligible is simply absent, and
 * the verse then stands alone, with a line saying so.
 */
export function PostEvidence({
  insight,
  headingLevel = 3,
}: {
  insight: PostInsight;
  headingLevel?: 2 | 3;
}) {
  const verses = insight.quran.map((verse) => (
    <EvidenceCard
      key={`${verse.surah}-${verse.ayah}`}
      variant="quran"
      headingLevel={headingLevel}
      text={verse.text}
      reference={M.quranReference(verse.surah_name, verse.ayah)}
      sourceHref={verse.source_url}
      verified={verse.verified}
    />
  ));
  const hadiths = insight.hadith.map((hadith) => (
    <EvidenceCard
      key={`${hadith.collection}-${hadith.number}`}
      variant="sunnah"
      headingLevel={headingLevel}
      text={hadith.text}
      reference={M.hadithReference(hadith.collection_name, hadith.number)}
      verifyHref={hadith.verification_url}
      ruling={hadith.classification}
      verified={hadith.verified}
    />
  ));
  return (
    <div className="flex flex-col gap-4" data-testid="post-evidence">
      <EvidencePair
        quran={<div className="flex flex-col gap-4">{verses}</div>}
        sunnah={
          hadiths.length === 0 ? undefined : <div className="flex flex-col gap-4">{hadiths}</div>
        }
      />
      {hadiths.length === 0 && verses.length > 0 ? (
        <p className="m-0 text-fg-muted text-sm">{M.verseAlone}</p>
      ) : null}
    </div>
  );
}
