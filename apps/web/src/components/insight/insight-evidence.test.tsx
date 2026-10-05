import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Insight } from '@/lib/scan/api';
import { HADITH_TEXT, insightOut, sha256, VERSE_TEXT } from '@/test/scan';
import { InsightEvidence } from './insight-evidence';

function bytes(text: string) {
  return Array.from(new TextEncoder().encode(text));
}

function hadithOf(insight: Insight) {
  return (insight.hadith as NonNullable<Insight['hadith']>).hadith;
}

describe('InsightEvidence', () => {
  it('renders the verse and the hadith byte for byte, and they match the stored hashes', () => {
    const insight = insightOut();
    const { container } = render(<InsightEvidence insight={insight} />);
    const verse = container.querySelector('[data-scripture="quran"]')?.textContent as string;
    const hadith = container.querySelector('[data-scripture="hadith"]')?.textContent as string;
    expect(bytes(verse)).toEqual(bytes(VERSE_TEXT));
    expect(bytes(hadith)).toEqual(bytes(HADITH_TEXT));
    expect(sha256(verse)).toBe(insight.quran?.verse.sha256);
    expect(sha256(hadith)).toBe(hadithOf(insight).sha256);
  });

  it('keeps a Uthmani mark, a direction mark and the spaces exactly as stored', () => {
    const { container } = render(<InsightEvidence insight={insightOut()} />);
    const verse = container.querySelector('[data-scripture="quran"]')?.textContent as string;
    expect(verse).toContain('\u0670');
    expect(verse).toContain('\u200F');
    expect(verse.endsWith(' ')).toBe(true);
    expect(verse).toContain('  ');
  });

  it('shows the reference, the ruling as recorded, its source and the links', () => {
    render(<InsightEvidence insight={insightOut()} />);
    const quran = screen.getByRole('article', { name: 'القرآن' });
    expect(within(quran).getByText('سورة اختبار، الآية 50')).toBeInTheDocument();
    expect(within(quran).queryByRole('link')).toBeNull();
    const sunnah = screen.getByRole('article', { name: 'السنة' });
    expect(within(sunnah).getByText('صحيح اختبار، رقم 1032')).toBeInTheDocument();
    expect(within(sunnah).getByText('حكم الدرر: إسناده صحيح')).toBeInTheDocument();
    expect(within(sunnah).getByText('محدّث الاختبار، كتاب الاختبار، 12')).toBeInTheDocument();
    expect(within(sunnah).getByRole('link', { name: /افتح المصدر/ })).toHaveAttribute(
      'href',
      'https://dorar.net/hadith/sharh/1'
    );
    expect(within(sunnah).getByRole('link', { name: /تحقق في الدرر/ })).toHaveAttribute(
      'href',
      'https://dorar.net/hadith/search?q=test'
    );
  });

  it('applies the display spans without cutting or changing the text', () => {
    const { container } = render(<InsightEvidence insight={insightOut()} />);
    const paragraph = container.querySelector('[data-scripture="hadith"]');
    expect(paragraph).toHaveAttribute('data-spans', 'applied');
    expect(
      Array.from(paragraph?.children ?? []).map((span) => span.getAttribute('data-role'))
    ).toEqual(['chain', 'words', 'tail']);
  });

  it('reads the API spans in code points, so a character outside the plane does not shift them', () => {
    const text = 'a\u{1F600} b c';
    const base = insightOut();
    const hadith = base.hadith as NonNullable<Insight['hadith']>;
    const insight = insightOut({
      hadith: {
        ...hadith,
        hadith: {
          ...hadith.hadith,
          text,
          sha256: sha256(text),
          // Code points: «a😀» is 0–2, the space and «b c» follow.
          spans: [
            { start: 0, end: 2, role: 'chain' },
            { start: 3, end: 6, role: 'words' },
          ],
        },
      },
    });
    const { container } = render(<InsightEvidence insight={insight} />);
    const paragraph = container.querySelector('[data-scripture="hadith"]');
    expect(paragraph).toHaveAttribute('data-spans', 'applied');
    expect(paragraph?.textContent).toBe(text);
    expect(paragraph?.querySelector('[data-role="chain"]')?.textContent).toBe('a\u{1F600}');
  });

  it('shows the verse alone, with the API notice, while the hadith waits for its ruling', () => {
    const insight = insightOut({
      hadith: null,
      hadith_status: 'awaiting_verification',
      notice: '[الحديث بانتظار الحكم]',
      pair_complete: false,
    });
    const { container } = render(<InsightEvidence insight={insight} />);
    expect(screen.getByRole('article', { name: 'القرآن' })).toBeInTheDocument();
    expect(screen.queryByRole('article', { name: 'السنة' })).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent('[الحديث بانتظار الحكم]');
    expect(container.querySelector('svg[focusable="false"][width="24"]')).toBeNull();
  });

  it('shows no notice when there is no hadith and none is awaited', () => {
    render(<InsightEvidence insight={insightOut({ hadith: null, hadith_status: 'none' })} />);
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByRole('article', { name: 'السنة' })).toBeNull();
  });

  it('shows a hadith without its verse, with no thread between', () => {
    render(<InsightEvidence insight={insightOut({ quran: null, pair_complete: false })} />);
    expect(screen.queryByRole('article', { name: 'القرآن' })).toBeNull();
    expect(screen.getByRole('article', { name: 'السنة' })).toBeInTheDocument();
  });

  it('gives both cards the heading level it is told, and h2 by default', () => {
    const { rerender } = render(<InsightEvidence insight={insightOut()} />);
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(2);
    rerender(<InsightEvidence insight={insightOut()} headingLevel={3} />);
    expect(screen.queryAllByRole('heading', { level: 2 })).toHaveLength(0);
    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(2);
  });

  it('marks the verse as matched to its source, as the API says it was', () => {
    render(<InsightEvidence insight={insightOut()} />);
    expect(screen.getByText('نص موثّق من مصدره')).toBeInTheDocument();
  });

  it('falls back to the search link and says no ruling is recorded when none was', () => {
    const base = insightOut();
    const hadith = base.hadith as NonNullable<Insight['hadith']>;
    const insight = insightOut({
      hadith: { ...hadith, hadith: { ...hadith.hadith, ruling: null } },
    });
    render(<InsightEvidence insight={insight} />);
    const sunnah = screen.getByRole('article', { name: 'السنة' });
    expect(within(sunnah).queryByText(/^حكم الدرر:/)).toBeNull();
    expect(
      within(sunnah).getByText('لم نسجّل حكم الدرر لهذا الحديث بعد؛ تحقّق منه في الدرر.')
    ).toBeInTheDocument();
    expect(within(sunnah).getByRole('link', { name: /افتح المصدر/ })).toHaveAttribute(
      'href',
      'https://dorar.net/hadith/search?q=test'
    );
  });

  it('puts two short texts side by side on wide screens, and two long ones one above the other', () => {
    const { container, rerender } = render(<InsightEvidence insight={insightOut()} />);
    expect(container.querySelector('.wide\\:grid')).not.toBeNull();
    const base = insightOut();
    const long = 'ا'.repeat(300);
    rerender(
      <InsightEvidence
        insight={insightOut({
          quran: {
            ...(base.quran as NonNullable<Insight['quran']>),
            verse: {
              ...(base.quran as NonNullable<Insight['quran']>).verse,
              text: long,
            },
          },
        })}
      />
    );
    expect(container.querySelector('.wide\\:grid')).toBeNull();
  });
});
