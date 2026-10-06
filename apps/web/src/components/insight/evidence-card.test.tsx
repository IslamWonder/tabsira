import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvidenceCard } from './evidence-card';
import type { HadithSpan } from './hadith-segments';

// Placeholders only (AGENTS.md: no verse or hadith is typed by hand). The
// strings carry the awkward parts of stored scripture on purpose: diacritics,
// a right-to-left mark, double spaces, a line break and a trailing space.
const VERSE = '[نصُّ  الآية\u200F يأتي من المدونة]\n[سطر ثانٍ] ';
const CHAIN = '[سند الحديث]، ';
const BODY = '[متن الحديث] "\u200F ';
const WORDS = '[كلمات النبي ﷺ]';
const TAIL = ' \u200F"\u200F. [تعليق]  ';
const HADITH = CHAIN + BODY + WORDS + TAIL;
const SPANS: HadithSpan[] = [
  { start: 0, end: CHAIN.length, role: 'chain' },
  { start: CHAIN.length, end: CHAIN.length + BODY.length, role: 'body' },
  {
    start: CHAIN.length + BODY.length,
    end: CHAIN.length + BODY.length + WORDS.length,
    role: 'words',
  },
  { start: HADITH.length - TAIL.length, end: HADITH.length, role: 'tail' },
];

function utf8(text: string) {
  return Array.from(new TextEncoder().encode(text));
}

describe('EvidenceCard, Quran', () => {
  function renderQuran() {
    render(<EvidenceCard variant="quran" text={VERSE} reference="[السورة · الآية]" />);
    return screen.getByRole('article', { name: 'القرآن الكريم' });
  }

  it('renders the verse byte for byte', () => {
    const card = renderQuran();
    const verse = card.querySelector('[data-scripture="quran"]');
    expect(verse?.textContent).toBe(VERSE);
    expect(utf8(verse?.textContent ?? '')).toEqual(utf8(VERSE));
  });

  it('sets the ornate brackets apart, in their own font, outside the verse', () => {
    const card = renderQuran();
    const paragraph = card.querySelector('[data-scripture="quran"]')?.parentElement;
    const [open, verse, close] = Array.from(paragraph?.children ?? []);
    expect(open?.textContent).toBe('﴿');
    expect(close?.textContent).toBe('﴾');
    expect(open).toHaveClass('font-ornament');
    expect(close).toHaveAttribute('aria-hidden', 'true');
    expect(verse?.textContent).not.toMatch(/[﴾﴿]/);
    expect(paragraph).toHaveClass('font-quran');
    expect(paragraph).toHaveAttribute('lang', 'ar');
  });

  it('shows its reference and no link', () => {
    const card = renderQuran();
    expect(within(card).getByText('[السورة · الآية]')).toBeInTheDocument();
    expect(within(card).queryByRole('link')).toBeNull();
    expect(within(card).getByRole('heading', { level: 2 })).toHaveTextContent('القرآن الكريم');
  });
});

describe('EvidenceCard, verified', () => {
  it('says the text matched its source only when the API says so', () => {
    render(<EvidenceCard variant="quran" verified text={VERSE} reference="[السورة · الآية]" />);
    expect(screen.getByText('نص موثّق من مصدره')).toBeInTheDocument();
  });
});

describe('EvidenceCard, Sunnah', () => {
  function renderSunnah(spans?: readonly HadithSpan[], text = HADITH) {
    const { unmount } = render(
      <EvidenceCard
        variant="sunnah"
        headingLevel={3}
        text={text}
        spans={spans}
        reference="[الكتاب · الرقم]"
        className="extra"
      />
    );
    return Object.assign(screen.getByRole('article', { name: 'السنة النبوية' }), { unmount });
  }

  it('renders the whole hadith byte for byte, cut only by position', () => {
    const card = renderSunnah(SPANS);
    const paragraph = card.querySelector('[data-scripture="hadith"]');
    expect(paragraph?.textContent).toBe(HADITH);
    expect(utf8(paragraph?.textContent ?? '')).toEqual(utf8(HADITH));
    expect(paragraph).toHaveAttribute('data-spans', 'applied');
    const roles = Array.from(paragraph?.children ?? []).map((span) => [
      span.getAttribute('data-role'),
      span.textContent,
    ]);
    expect(roles).toEqual([
      ['chain', CHAIN],
      ['body', BODY],
      ['words', WORDS],
      ['tail', TAIL],
    ]);
  });

  it('sets the chain quieter and the words stronger', () => {
    const card = renderSunnah(SPANS);
    expect(card.querySelector('[data-role="chain"]')).toHaveClass('text-fg-muted');
    expect(card.querySelector('[data-role="tail"]')).toHaveClass('text-fg-muted');
    expect(card.querySelector('[data-role="words"]')).toHaveClass('font-bold');
    expect(card.querySelector('[data-role="body"]')).not.toHaveAttribute('class');
  });

  it('shows the text whole and unstyled when the spans are unusable', () => {
    const card = renderSunnah([{ start: 2, end: 5, role: 'words' }]);
    const paragraph = card.querySelector('[data-scripture="hadith"]');
    expect(paragraph).toHaveAttribute('data-spans', 'ignored');
    expect(paragraph?.children).toHaveLength(1);
    expect(paragraph?.textContent).toBe(HADITH);
  });

  it('shows the text whole without spans', () => {
    for (const spans of [undefined, []]) {
      const card = renderSunnah(spans);
      const paragraph = card.querySelector('[data-scripture="hadith"]');
      expect(paragraph).toHaveAttribute('data-spans', 'none');
      expect(paragraph?.textContent).toBe(HADITH);
      card.unmount();
    }
  });

  it('shows its heading and class, and no link, ruling or verified chip', () => {
    const card = renderSunnah(SPANS);
    expect(card).toHaveClass('extra');
    expect(within(card).getByRole('heading', { level: 3 })).toHaveTextContent('السنة النبوية');
    expect(within(card).queryByRole('link')).toBeNull();
    expect(within(card).queryByText(/الدرر|حكم|تصنيف/)).toBeNull();
    expect(within(card).queryByText('نص موثّق من مصدره')).toBeNull();
  });
});
