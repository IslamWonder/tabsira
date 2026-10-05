import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { mockApi } from '@/test/api';
import { insightOut } from '@/test/scan';
import { LearnedInsight } from './learned-insight';

describe('LearnedInsight', () => {
  it('names a hadith alone, by its reference, with no ruling line', async () => {
    mockApi({
      'GET /insights/9001': {
        body: insightOut({
          id: '9001',
          quran: null,
          chat: { enabled: true, closed: true, used: 0, limit: 3, remaining: 3, messages: [] },
        }),
      },
    });
    render(<LearnedInsight id="9001" onGoTo={vi.fn()} />);

    expect(await screen.findByText('صحيح اختبار · 1032')).toBeInTheDocument();
    expect(screen.queryByText(/القرآن/)).toBeNull();
    expect(screen.queryByText(/الدرر/)).toBeNull();
    expect(screen.queryByRole('link', { name: /تحقق/ })).toBeNull();
    expect(screen.queryByRole('link', { name: 'حاور بصيرتك' })).toBeNull();
  });

  it('drops an answer that arrives after it closed', async () => {
    let answer: (value: Response) => void = () => undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            answer = resolve;
          })
      )
    );
    const { unmount } = render(<LearnedInsight id="9001" onGoTo={vi.fn()} />);
    unmount();
    answer(
      new Response(JSON.stringify(insightOut({ id: '9001' })), {
        headers: { 'Content-Type': 'application/json' },
      })
    );
    await Promise.resolve();
    expect(screen.queryByRole('article')).toBeNull();
  });
});

describe('LearnedInsight, what kind of insight it is', () => {
  it('says a prepared example is one', async () => {
    const prepared = insightOut({ id: '9001', engine: 'prepared', label: 'مثال موثّق مُعدّ' });
    const hadith = prepared.hadith as NonNullable<typeof prepared.hadith>;
    mockApi({
      'GET /insights/9001': {
        body: {
          ...prepared,
          hadith: { ...hadith, hadith: { ...hadith.hadith, arabic_number: '١٠٣٢' } },
        },
      },
    });
    render(<LearnedInsight id="9001" onGoTo={vi.fn()} />);

    expect(await screen.findByText('مثال موثّق مُعدّ')).toBeInTheDocument();
    // Numbered as the insight's own screen numbers it.
    expect(screen.getByText('صحيح اختبار · 1032')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /تحقق في الدرر/ })).toBeNull();
  });
});

describe('LearnedInsight, a verse alone', () => {
  it('names the verse when the insight shows no hadith', async () => {
    mockApi({ 'GET /insights/9001': { body: insightOut({ id: '9001', hadith: null }) } });
    render(<LearnedInsight id="9001" onGoTo={vi.fn()} />);

    expect(await screen.findByText('سورة اختبار · 50')).toBeInTheDocument();
    expect(screen.queryByText(/صحيح اختبار/)).toBeNull();
  });
});
