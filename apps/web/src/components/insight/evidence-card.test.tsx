import { cleanup, render, screen, within } from '@testing-library/react';
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
    render(
      <EvidenceCard
        variant="quran"
        text={VERSE}
        reference="[السورة · الآية]"
        sourceHref="https://quranpedia.net/"
      />
    );
    return screen.getByRole('article', { name: 'القرآن' });
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

  it('shows its reference and opens the source in a new tab', () => {
    const card = renderQuran();
    expect(within(card).getByText('[السورة · الآية]')).toBeInTheDocument();
    const link = within(card).getByRole('link', { name: /افتح في قرآنبيديا/ });
    expect(link).toHaveAttribute('href', 'https://quranpedia.net/');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(within(card).queryByRole('link', { name: /الدرر/ })).toBeNull();
    expect(within(card).getByRole('heading', { level: 2 })).toHaveTextContent('القرآن');
  });
});

describe('EvidenceCard, verified', () => {
  it('says the text matched its source only when the API says so', () => {
    render(
      <EvidenceCard
        variant="quran"
        verified
        text={VERSE}
        reference="[السورة · الآية]"
        sourceHref="https://quranpedia.net/"
      />
    );
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
        sourceHref="https://example.org/source"
        verifyHref="https://dorar.net/"
        className="extra"
      />
    );
    return Object.assign(screen.getByRole('article', { name: 'السنة' }), { unmount });
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

  it('links to its source and to its ruling on dorar.net', () => {
    const card = renderSunnah(SPANS);
    expect(card).toHaveClass('extra');
    expect(within(card).getByRole('heading', { level: 3 })).toHaveTextContent('السنة');
    expect(within(card).getByRole('link', { name: /افتح المصدر/ })).toHaveAttribute(
      'href',
      'https://example.org/source'
    );
    const verify = within(card).getByRole('link', { name: /تحقق في الدرر/ });
    expect(verify).toHaveAttribute('href', 'https://dorar.net/');
    expect(verify).toHaveAccessibleName(/يفتح في نافذة جديدة/);
  });
});

describe('EvidenceCard, the ruling', () => {
  function renderRuled(extra: { ruling?: string; rulingSource?: string }) {
    render(
      <EvidenceCard
        variant="sunnah"
        text={HADITH}
        reference="[الكتاب · الرقم]"
        sourceHref="https://example.org/source"
        verifyHref="https://dorar.net/"
        {...extra}
      />
    );
    return screen.getByRole('article', { name: 'السنة' });
  }

  it('gives the ruling as recorded, and under it who gave it and where', () => {
    const card = renderRuled({ ruling: '[الحكم]', rulingSource: '[المحدّث، الكتاب، الصفحة]' });
    expect(within(card).getByText('حكم الدرر: [الحكم]')).toBeInTheDocument();
    expect(within(card).getByText('[المحدّث، الكتاب، الصفحة]')).toBeInTheDocument();
  });

  it('gives the ruling alone when its source is not known, and says so when there is none', () => {
    const alone = renderRuled({ ruling: '[الحكم]' });
    expect(within(alone).queryByText(/المحدّث/)).toBeNull();
    expect(
      within(alone).queryByText('لم نسجّل حكم الدرر لهذا الحديث بعد؛ تحقّق منه في الدرر.')
    ).toBeNull();
    cleanup();
    // DECISIONS.md 58: a hadith may show before any ruling; the card never invents one.
    const none = renderRuled({});
    expect(within(none).queryByText(/^حكم الدرر:/)).toBeNull();
    expect(
      within(none).getByText('لم نسجّل حكم الدرر لهذا الحديث بعد؛ تحقّق منه في الدرر.')
    ).toBeInTheDocument();
  });
});

describe("EvidenceCard, Sunnah with the editor's classification only", () => {
  it("labels the classification as the editor's, keeps the dorar link, and omits the missing source link", () => {
    render(
      <EvidenceCard
        variant="sunnah"
        headingLevel={3}
        text="[نص الحديث]"
        reference="[الكتاب · الرقم]"
        verifyHref="https://dorar.net/"
        classification="[تصنيف]"
      />
    );
    const card = screen.getByRole('article', { name: 'السنة' });
    expect(within(card).getByText('تصنيف المحرّر لحكم الدرر: [تصنيف]')).toBeInTheDocument();
    expect(within(card).queryByText(/^حكم الدرر:/)).toBeNull();
    expect(within(card).getByRole('link', { name: /تحقق في الدرر/ })).toHaveAttribute(
      'href',
      'https://dorar.net/'
    );
    expect(within(card).queryByRole('link', { name: /افتح المصدر/ })).toBeNull();
  });
});
