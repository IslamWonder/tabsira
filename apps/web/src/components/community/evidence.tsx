import { EvidenceCard } from '@/components/insight/evidence-card';
import { EvidencePair } from '@/components/insight/evidence-pair';
import { messages } from '@/messages';
import type { PostInsight } from '@/social/types';

const M = messages.community.post;

/**
 * The verified pair of a post, exactly as the API returned it from the
 * scripture store: the text goes to the card untouched (AGENTS.md: byte for
 * byte, never typed or changed here). A publication may cite up to three of
 * each kind; when the gate kept no hadith, the verse stands alone, with a line saying so.
 */
export function PostEvidence({
  insight,
  headingLevel = 3,
}: Readonly<{
  /** What a post or an atlas entry cites: the verses and the hadiths, as the API returned them. */
  insight: Pick<PostInsight, 'quran' | 'hadith'>;
  headingLevel?: 2 | 3;
}>) {
  const verses = insight.quran.map((verse) => (
    <EvidenceCard
      key={`${verse.surah}-${verse.ayah}`}
      variant="quran"
      headingLevel={headingLevel}
      text={verse.text}
      reference={M.quranReference(verse.surah_name, verse.ayah)}
    />
  ));
  const hadiths = insight.hadith.map((hadith) => (
    <EvidenceCard
      key={`${hadith.collection}-${hadith.number}`}
      variant="sunnah"
      headingLevel={headingLevel}
      text={hadith.text}
      reference={M.hadithReference(hadith.collection_name, hadith.number)}
    />
  ));
  const quranBlock = <div className="flex flex-col gap-4">{verses}</div>;
  const sunnahBlock = <div className="flex flex-col gap-4">{hadiths}</div>;
  return (
    <div className="flex flex-col gap-4" data-testid="post-evidence">
      {/* The thread of the pair joins two sources, never one. */}
      {verses.length > 0 && hadiths.length > 0 ? (
        <EvidencePair quran={quranBlock} sunnah={sunnahBlock} />
      ) : null}
      {verses.length > 0 && hadiths.length === 0 ? quranBlock : null}
      {verses.length === 0 && hadiths.length > 0 ? sunnahBlock : null}
      {hadiths.length === 0 && verses.length > 0 ? (
        <p className="m-0 text-fg-muted text-sm">{M.verseAlone}</p>
      ) : null}
      {verses.length === 0 && hadiths.length > 0 ? (
        <p className="m-0 text-fg-muted text-sm">{M.hadithAlone}</p>
      ) : null}
      {verses.length === 0 && hadiths.length === 0 ? (
        <p className="m-0 text-fg-muted text-sm">{M.noEvidence}</p>
      ) : null}
    </div>
  );
}
