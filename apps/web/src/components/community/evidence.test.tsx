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

  it('says plainly when no verified text is shown', () => {
    render(<PostEvidence insight={{ quran: [], hadith: [] }} />);
    expect(screen.getByTestId('post-evidence')).toHaveTextContent(
      'لا نص موثّق يُعرض مع هذه البصيرة الآن.'
    );
    expect(document.querySelector('[data-scripture]')).toBeNull();
  });
});
