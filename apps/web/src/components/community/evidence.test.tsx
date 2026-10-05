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

  it('shows a hadith with no ruling, no link and no verified chip', () => {
    const [hadith] = POST.insight.hadith;
    if (hadith === undefined) {
      throw new Error('the fixture post cites a hadith');
    }
    render(<PostEvidence insight={{ quran: [], hadith: [hadith] }} />);
    expect(screen.queryByText(/الدرر|تصنيف/)).toBeNull();
    expect(screen.queryByRole('link')).toBeNull();
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
