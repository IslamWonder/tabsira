import { useId } from 'react';
import { OrnateCorners } from '@/components/fx/ornate-corners';
import { CheckIcon, ExternalIcon } from '@/components/icons';
import { Chip } from '@/components/ui/chip';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { type HadithRole, type HadithSpan, segmentHadith, spansAreValid } from './hadith-segments';

interface EvidenceBase {
  /** The stored text, rendered exactly as given: never trimmed, joined, shortened or normalised. */
  text: string;
  /** Where the text comes from, e.g. the surah and verse number, or the book and hadith number. */
  reference: string;
  /** The text on its source site: the verse's quranpedia page, the hadith's source. */
  sourceHref: string;
  /** Level of the card's heading in the page outline. */
  headingLevel?: 2 | 3;
  /** The API matched the displayed text to its stored hash: say so beside the label. */
  verified?: boolean;
  className?: string;
}

export interface QuranEvidenceProps extends EvidenceBase {
  variant: 'quran';
}

export interface SunnahEvidenceProps extends EvidenceBase {
  variant: 'sunnah';
  /** Presentation spans over `text`; see hadith-segments.ts. */
  spans?: readonly HadithSpan[];
  /** The hadith's ruling on dorar.net, opened by the reader (DECISIONS.md 18). */
  verifyHref: string;
  /** The ruling as an editor recorded it from dorar.net, word for word. */
  ruling?: string;
}

export type EvidenceCardProps = QuranEvidenceProps | SunnahEvidenceProps;

// The chain and the closing notes recede; the Prophet's words stand out. Size,
// weight and colour only: no character is added or removed.
const ROLE_CLASSES: Record<HadithRole, string> = {
  chain: 'text-[0.9375rem] text-fg-muted',
  body: '',
  words:
    'font-bold text-[1.375rem] text-[var(--hadith-words)] [text-shadow:var(--hadith-words-glow)] ' +
    'bg-[linear-gradient(transparent_62%,var(--hadith-highlight)_62%)] box-decoration-clone',
  tail: 'text-[0.9375rem] text-fg-muted',
};

function ExternalLink({ href, children }: { href: string; children: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex min-h-12 shrink-0 items-center gap-1.5 font-medium text-[0.875rem] text-link underline-offset-4 hover:underline"
    >
      {children}
      <span className="sr-only"> {messages.a11y.opensInNewTab}</span>
      <ExternalIcon />
    </a>
  );
}

/**
 * One piece of evidence: the Quran (ivory script on a gold wash at night, mint
 * card by day) or the Sunnah. The label, the reference and the source link are
 * shown with the text, never a tap away (tajriba §3.3), and the two cards keep
 * the same anatomy (Law of Similarity) so the second one reads at a glance.
 */
export function EvidenceCard(props: EvidenceCardProps) {
  const labelId = useId();
  const isQuran = props.variant === 'quran';
  const Heading = props.headingLevel === 3 ? 'h3' : 'h2';

  return (
    <article
      aria-labelledby={labelId}
      data-variant={props.variant}
      className={cx(
        // An illuminated frame (gold double rule, khatam corners) around the text, never behind it.
        'fx-ornate relative flex flex-col gap-3 rounded-[var(--radius-panel)] px-6 pt-4 pb-6',
        isQuran ? 'surface-quran' : 'surface-sunnah',
        props.className
      )}
    >
      <OrnateCorners />
      <header className="flex items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Heading id={labelId} className="m-0 text-base">
            <Chip tone={props.variant}>
              {isQuran ? messages.evidence.quran : messages.evidence.sunnah}
            </Chip>
          </Heading>
          <span className="text-[0.8125rem] text-fg-soft">{props.reference}</span>
          {props.verified ? (
            <Chip tone="primary" icon={<CheckIcon width="13" height="13" />}>
              {messages.evidence.verified}
            </Chip>
          ) : null}
        </div>
        {props.variant === 'quran' ? (
          <ExternalLink href={props.sourceHref}>{messages.evidence.openQuranpedia}</ExternalLink>
        ) : (
          <ExternalLink href={props.verifyHref}>{messages.evidence.verifyDorar}</ExternalLink>
        )}
      </header>

      {props.variant === 'quran' ? (
        <p
          lang="ar"
          dir="rtl"
          className="m-0 whitespace-pre-wrap text-justify font-quran text-[1.625rem] text-quran-text leading-[2.2]"
        >
          {/* The ornate brackets are their own elements, in Amiri, never part of the verse text. */}
          <span aria-hidden="true" className="font-ornament text-quran">
            {messages.evidence.quranOpen}
          </span>
          <span data-scripture="quran">{props.text}</span>
          <span aria-hidden="true" className="font-ornament text-quran">
            {messages.evidence.quranClose}
          </span>
        </p>
      ) : (
        <HadithText text={props.text} spans={props.spans} />
      )}

      {props.variant === 'sunnah' ? (
        <footer className="flex flex-wrap items-center justify-between gap-x-4 border-[var(--sunnah-border)] border-t pt-1">
          {props.ruling === undefined ? (
            <span />
          ) : (
            <p className="m-0 text-[0.8125rem] text-fg-muted">
              {messages.evidence.ruling(props.ruling)}
            </p>
          )}
          <ExternalLink href={props.sourceHref}>{messages.evidence.openSource}</ExternalLink>
        </footer>
      ) : null}
    </article>
  );
}

function spanStatus(text: string, spans: readonly HadithSpan[] | undefined) {
  if (spans === undefined || spans.length === 0) {
    return 'none';
  }
  return spansAreValid(text, spans) ? 'applied' : 'ignored';
}

function HadithText({ text, spans }: { text: string; spans: readonly HadithSpan[] | undefined }) {
  return (
    <p
      lang="ar"
      dir="rtl"
      data-scripture="hadith"
      data-spans={spanStatus(text, spans)}
      className="m-0 whitespace-pre-wrap font-hadith text-[1.1875rem] text-fg leading-[2]"
    >
      {segmentHadith(text, spans).map((segment) => (
        <span
          key={segment.start}
          data-role={segment.role}
          className={ROLE_CLASSES[segment.role] || undefined}
        >
          {text.slice(segment.start, segment.end)}
        </span>
      ))}
    </p>
  );
}
