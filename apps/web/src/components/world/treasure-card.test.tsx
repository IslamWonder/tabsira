import { createHash } from 'node:crypto';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { BURST_EVENT } from '@/components/fx/burst';
import { apiError, mockApi } from '@/test/api';
import { HADITH_SHA256, HADITH_TEXT, QURAN_SHA256, QURAN_TEXT, TREASURE } from '@/test/world';
import type { Treasure } from '@/world/api';
import { TreasureCard } from './treasure-card';

const sha256 = (text: string) => createHash('sha256').update(text).digest('hex');

async function reveal(body: Treasure) {
  mockApi({ 'POST /world/treasures/8001/reveal': { body } });
  render(<TreasureCard id="8001" />);
  await userEvent.click(screen.getByRole('button', { name: 'اكشف الكنز' }));
  return screen.findByRole('heading', { level: 3, name: 'كشفت كنزًا' });
}

describe('TreasureCard', () => {
  it('invites quietly and knows nothing of the treasure before the reveal', () => {
    mockApi({});
    render(<TreasureCard id="8001" />);
    expect(screen.getByRole('heading', { level: 3, name: 'كنز مخبوء' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'اكشف الكنز' })).toBeEnabled();
  });

  it('shows the verses and the hadith exactly as the API stored them, with a burst of light', async () => {
    const burst = vi.fn();
    window.addEventListener(BURST_EVENT, burst);
    await reveal(TREASURE);
    window.removeEventListener(BURST_EVENT, burst);
    expect(burst).toHaveBeenCalledOnce();
    const quran = document.querySelector('[data-scripture="quran"]');
    const hadith = document.querySelector('[data-scripture="hadith"]');
    // What is on screen is what the store returned, and it still matches its stored hash.
    expect(quran?.textContent).toBe(QURAN_TEXT);
    expect(hadith?.textContent).toBe(HADITH_TEXT);
    expect(sha256(quran?.textContent ?? '')).toBe(QURAN_SHA256);
    expect(sha256(hadith?.textContent ?? '')).toBe(HADITH_SHA256);
    expect(screen.getByText('[اسم السورة] · 50')).toBeInTheDocument();
    expect(screen.getByText('[اسم الكتاب] · [١٠٣٢]')).toBeInTheDocument();
    expect(screen.getByText('حكم الدرر: [نص الحكم]')).toBeInTheDocument();
    expect(screen.getByText('وحدة من المسار: [وحدة من المسار]')).toBeInTheDocument();
    expect(screen.getByText('[نوع الكنز]')).toBeInTheDocument();
    expect(screen.getByText('[إفصاح الكنز]')).toBeInTheDocument();
  });

  it('shows one text alone when the treasure has one, and the plain number when there is no Arabic one', async () => {
    const hadithOnly: Treasure = {
      ...TREASURE,
      quran: null,
      learning_unit: null,
      hadith: TREASURE.hadith && {
        ...TREASURE.hadith,
        hadith: { ...TREASURE.hadith.hadith, arabic_number: null, ruling: null },
      },
    };
    await reveal(hadithOnly);
    expect(document.querySelector('[data-scripture="quran"]')).toBeNull();
    expect(screen.getByText('[اسم الكتاب] · 1032')).toBeInTheDocument();
    expect(screen.queryByText(/حكم الدرر/)).toBeNull();
    expect(screen.queryByText(/وحدة من المسار/)).toBeNull();
  });

  it('shows a verse alone', async () => {
    await reveal({ ...TREASURE, hadith: null });
    expect(document.querySelector('[data-scripture="hadith"]')).toBeNull();
    expect(document.querySelector('[data-scripture="quran"]')).not.toBeNull();
  });

  it('says it is not time yet before the return, and lets the reader come back', async () => {
    mockApi({ 'POST /world/treasures/8001/reveal': apiError(409, 'treasure_not_ready') });
    render(<TreasureCard id="8001" />);
    await userEvent.click(screen.getByRole('button', { name: 'اكشف الكنز' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('لم يحن وقته بعد');
    expect(screen.getByRole('button', { name: 'اكشف الكنز' })).toBeEnabled();
  });

  it('says what went wrong for any other failure', async () => {
    mockApi({ 'POST /world/treasures/8001/reveal': 'network-error' });
    render(<TreasureCard id="8001" />);
    await userEvent.click(screen.getByRole('button', { name: 'اكشف الكنز' }));
    expect(await screen.findByRole('alert')).not.toHaveTextContent('لم يحن وقته بعد');
  });

  it('shows that it is working, and cannot be pressed twice', async () => {
    mockApi({ 'POST /world/treasures/8001/reveal': () => new Promise(() => undefined) });
    render(<TreasureCard id="8001" />);
    await userEvent.click(screen.getByRole('button', { name: 'اكشف الكنز' }));
    expect(screen.getByRole('button', { name: 'نكشفه…' })).toBeDisabled();
  });
});
