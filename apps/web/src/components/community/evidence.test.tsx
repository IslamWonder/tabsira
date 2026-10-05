import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { HADITH_TEXT, POST } from '@/test/social';
import { PostEvidence } from './evidence';

describe('PostEvidence', () => {
  it('shows the hadith alone, byte for byte, and says the insight rests on it alone', () => {
    render(<PostEvidence insight={{ quran: [], hadith: POST.insight.hadith }} />);
    expect(document.querySelector('[data-scripture="hadith"]')?.textContent).toBe(HADITH_TEXT);
    expect(document.querySelector('[data-scripture="quran"]')).toBeNull();
    expect(screen.getByText('تستند هذه البصيرة إلى الحديث وحده.')).toBeInTheDocument();
  });

  it("gives the editor's classification, or says no ruling is recorded yet", () => {
    const [hadith] = POST.insight.hadith;
    if (hadith === undefined) {
      throw new Error('the fixture post cites a hadith');
    }
    const { unmount } = render(<PostEvidence insight={{ quran: [], hadith: [hadith] }} />);
    expect(screen.queryByText('لم نسجّل حكم الدرر لهذا الحديث بعد؛ تحقّق منه في الدرر.')).toBeNull();
    unmount();
    // DECISIONS.md 58: a hadith of the enriched file may show before any ruling.
    render(<PostEvidence insight={{ quran: [], hadith: [{ ...hadith, classification: null }] }} />);
    expect(
      screen.getByText('لم نسجّل حكم الدرر لهذا الحديث بعد؛ تحقّق منه في الدرر.')
    ).toBeInTheDocument();
    expect(screen.queryByText('نص موثّق من مصدره')).toBeNull();
    expect(document.querySelector('[data-scripture="hadith"]')?.textContent).toBe(HADITH_TEXT);
  });

  it('says plainly when no verified text is shown', () => {
    render(<PostEvidence insight={{ quran: [], hadith: [] }} />);
    expect(screen.getByTestId('post-evidence')).toHaveTextContent(
      'لا نص موثّق يُعرض مع هذه البصيرة الآن.'
    );
    expect(document.querySelector('[data-scripture]')).toBeNull();
  });
});
