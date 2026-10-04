import type { CSSProperties, ReactElement } from 'react';
import { type PublicInsight, publicInsightPath } from '@/lib/public-insight';
import { CARD_FONT_FAMILY, drawable } from '@/lib/share-card-fonts';
import { messages } from '@/messages';

/*
 * The share card (master prompt v2 §18): the insight's title and glimpse, the
 * verse and the hadith by their references with the hadith's ruling, one line of
 * the explanation, the brand, the disclosure and the link, at 1200×630 in one
 * real Arabic face (docs/SEO.md §2). The card never draws Quran or hadith text:
 * the image renderer drops vowel marks and changes letter joining, so it cannot
 * print a stored text byte for byte; the texts are read on the page, which the
 * card says. The layout is built for the renderer: flex boxes, inline styles,
 * `direction` on every text node. Every string goes through `drawable`, which
 * keeps the renderer from fetching a font elsewhere for a character the card
 * fonts lack (share-card-fonts.ts).
 */

export const CARD_WIDTH = 1200;
export const CARD_HEIGHT = 630;
/** The explanation line is platform text and may be cut; scripture never is. */
const EXPLANATION_MAX = 140;

const NIGHT = '#0B1210';
const IVORY = '#EEF3EF';
const SOFT = '#C3D4CC';
const MUTED = '#8FA39A';
const GOLD = '#E6C77F';
const FRAME = '#B28B38';
const EMERALD = '#3FD69A';

const rtl: CSSProperties = { direction: 'rtl', textAlign: 'right' };

/** Cut a platform text at a word so it fits `max` characters, with an ellipsis. */
export function clipLine(text: string, max: number): string {
  const points = Array.from(text.trim());
  if (points.length <= max) {
    return points.join('');
  }
  const room = points.slice(0, max - 1).join('');
  const cut = room.lastIndexOf(' ');
  return `${(cut > max / 2 ? room.slice(0, cut) : room).trimEnd()}…`;
}

function Reference({
  tag,
  reference,
  ruling,
}: {
  tag: string;
  reference: string;
  ruling?: string;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'row', gap: 14, alignItems: 'baseline' }}>
      <span style={{ ...rtl, fontWeight: 600, fontSize: 22, color: GOLD }}>{tag}</span>
      <span style={{ ...rtl, fontWeight: 500, fontSize: 26, color: IVORY }}>{reference}</span>
      {ruling === undefined ? null : (
        <span style={{ ...rtl, fontWeight: 500, fontSize: 20, color: EMERALD }}>{ruling}</span>
      )}
    </div>
  );
}

/** The card as an element tree for the image renderer. `origin` is the site's, for the link line. */
export function shareCard(
  insight: PublicInsight,
  origin: URL,
  covered: ReadonlySet<number>
): ReactElement {
  const text = (platform: string) => drawable(platform, covered);
  const verse = insight.quran?.verse;
  const hadith = insight.hadith?.hadith;
  const explanation = insight.explanation.find((part) => part.section !== 'seen');
  const T = messages.share.card;
  return (
    <div
      style={{
        width: CARD_WIDTH,
        height: CARD_HEIGHT,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        padding: '44px 56px',
        backgroundColor: NIGHT,
        backgroundImage:
          'radial-gradient(circle at 85% 0%, rgba(31,158,110,0.22), rgba(31,158,110,0) 70%)',
        color: IVORY,
        fontFamily: CARD_FONT_FAMILY,
        border: `1px solid ${FRAME}`,
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between' }}>
        <span style={{ ...rtl, fontWeight: 600, fontSize: 30, color: FRAME }}>{T.brand}</span>
        <div style={{ display: 'flex', flexDirection: 'row', gap: 18 }}>
          {insight.label === null ? null : (
            <span style={{ ...rtl, fontSize: 20, fontWeight: 600, color: GOLD }}>
              {text(insight.label)}
            </span>
          )}
          <span style={{ ...rtl, fontSize: 20, fontWeight: 500, color: EMERALD }}>
            {text(insight.relation_label)}
          </span>
        </div>
      </div>
      <h1
        style={{ ...rtl, margin: 0, fontWeight: 600, fontSize: 44, lineHeight: 1.3, color: GOLD }}
      >
        {text(insight.title)}
      </h1>
      <p style={{ ...rtl, margin: 0, fontSize: 26, fontWeight: 500, lineHeight: 1.6, color: SOFT }}>
        {text(insight.glimpse)}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {verse === undefined || insight.quran === null ? null : (
          <Reference
            tag={text(insight.quran.tag)}
            reference={text(messages.insightPage.verseReference(verse.surah_name, verse.ayah))}
          />
        )}
        {hadith === undefined || insight.hadith === null ? null : (
          <Reference
            tag={text(insight.hadith.tag)}
            reference={text(
              messages.insightPage.hadithReference(hadith.collection.name_ar, hadith.number)
            )}
            ruling={hadith.ruling === null ? undefined : text(hadith.ruling.ruling_text)}
          />
        )}
        {verse === undefined && hadith === undefined ? null : (
          <span style={{ ...rtl, fontSize: 20, fontWeight: 500, color: MUTED }}>
            {T.fullTextOnPage}
          </span>
        )}
      </div>
      {explanation === undefined ? null : (
        <div style={{ display: 'flex', flexDirection: 'row', gap: 12, alignItems: 'baseline' }}>
          <span style={{ ...rtl, fontSize: 18, fontWeight: 600, color: EMERALD }}>
            {text(insight.explanation_tag)}
          </span>
          <p
            style={{
              ...rtl,
              margin: 0,
              fontSize: 22,
              fontWeight: 500,
              lineHeight: 1.6,
              color: SOFT,
            }}
          >
            {text(clipLine(explanation.text, EXPLANATION_MAX))}
          </p>
        </div>
      )}
      <div
        style={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between', gap: 24 }}
      >
        <span style={{ direction: 'ltr', fontSize: 20, fontWeight: 500, color: MUTED }}>
          {text(`${origin.host}${publicInsightPath(insight.id)}`)}
        </span>
        <span style={{ ...rtl, fontSize: 16, fontWeight: 500, color: MUTED }}>
          {text(messages.disclosure.ai)}
        </span>
        {insight.author === null ? (
          <span />
        ) : (
          <span style={{ ...rtl, fontSize: 20, fontWeight: 500, color: MUTED }}>
            {text(T.byAuthor(insight.author.public_name))}
          </span>
        )}
      </div>
    </div>
  );
}
