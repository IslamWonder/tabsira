import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CaptureProvider } from '@/components/capture/capture-provider';
import { messages } from '@/messages';
import { apiError, mockApi } from '@/test/api';
import { PROGRESS, PROGRESS_COMPLETE, PROGRESS_EMPTY } from '@/test/world';
import { ProgressScreen } from './progress-screen';
import { questEntries } from './quest-card';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  usePathname: () => '/me/practice',
}));

/** The page renders inside the app's shell, whose capture sheet the empty sky opens. */
function screenInShell() {
  return render(
    <CaptureProvider>
      <ProgressScreen />
    </CaptureProvider>
  );
}

async function open(body = PROGRESS) {
  const api = mockApi({ 'GET /me/progress': { body } });
  screenInShell();
  await screen.findByRole('heading', { level: 2, name: body.rank.title });
  return api;
}

describe('ProgressScreen states', () => {
  it('says it is loading, and always offers the way back to «ملفي»', () => {
    mockApi({});
    screenInShell();
    expect(screen.getByRole('status')).toHaveTextContent('نحمّل معانيك…');
    expect(screen.getByRole('heading', { level: 1, name: 'تمرينك' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'ملفي' })).toHaveAttribute('href', '/me');
  });

  it('offers to try again when the practice could not be loaded', async () => {
    let calls = 0;
    mockApi({
      'GET /me/progress': () => {
        calls += 1;
        return calls === 1 ? apiError(500, 'internal_error') : { body: PROGRESS };
      },
    });
    screenInShell();
    expect(await screen.findByRole('alert')).toHaveTextContent('تعذّر تحميل معانيك');
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(await screen.findByRole('heading', { level: 2, name: '[مرتبة]' })).toBeInTheDocument();
  });

  it('sends the device time zone so that «today» is the learner day', async () => {
    const api = await open();
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    expect(new URL(api.requests[0]?.url ?? '').searchParams.get('tz')).toBe(zone);
  });
});

describe('ProgressScreen content', () => {
  it('frames everything as practice and closes with the API disclaimer', async () => {
    await open();
    expect(screen.getByText(/لا مقارنة بأحد، ولا حكم على إيمانك/)).toBeInTheDocument();
    expect(screen.getByText('[تنبيه التمرين]')).toBeInTheDocument();
  });

  it('shows the rank with the way to the next one', async () => {
    await open();
    const bar = screen.getByRole('progressbar', { name: 'الطريق إلى المرتبة التالية' });
    expect(bar).toHaveAttribute('aria-valuenow', '25');
    expect(bar).toHaveAttribute(
      'aria-valuetext',
      'المرتبة التالية «[المرتبة التالية]» عند 10 نظرة.'
    );
    expect(screen.getByText('[تلميح المرتبة]')).toBeInTheDocument();
    expect(screen.getByText('4 نظرة مكتملة')).toBeInTheDocument();
  });

  it('says plainly when the top rank is reached', async () => {
    await open(PROGRESS_COMPLETE);
    expect(screen.getByRole('progressbar')).toHaveAttribute(
      'aria-valuetext',
      messages.practiceView.rank.top
    );
  });

  it('shows the streak and the last seven days, today first', async () => {
    await open();
    expect(screen.getByRole('heading', { level: 2, name: '3 أيام متتالية' })).toBeInTheDocument();
    expect(screen.getByText('أطول سلسلة لك: 5')).toBeInTheDocument();
    const days = within(screen.getByRole('list', { name: 'آخر سبعة أيام' })).getAllByRole(
      'listitem'
    );
    expect(days).toHaveLength(7);
    expect(days[0]).toHaveTextContent('اليوم');
    expect(days[0]).toHaveTextContent('نظرت');
    expect(days[3]).toHaveTextContent('لم تنظر');
  });

  it('says one day in the singular', async () => {
    await open(PROGRESS_EMPTY);
    expect(screen.getByRole('heading', { level: 2, name: 'يوم واحد متتالٍ' })).toBeInTheDocument();
  });

  it('shows the daily quest with the API labels and the current step', async () => {
    await open();
    expect(screen.getByRole('heading', { level: 2, name: '[مهمة اليوم]' })).toBeInTheDocument();
    expect(screen.getByText('مهمة اليوم لم تكتمل بعد')).toBeInTheDocument();
    expect(screen.getByText('أتممتها في 2 أيام حتى الآن')).toBeInTheDocument();
    expect(screen.getByText('[خطوة الإتمام]').closest('li')).toHaveAttribute(
      'aria-current',
      'step'
    );
  });

  it('marks a finished quest done, with no current step', async () => {
    await open(PROGRESS_COMPLETE);
    expect(screen.getByText('أتممت مهمة اليوم')).toBeInTheDocument();
    expect(document.querySelector('[aria-current="step"]')).toBeNull();
  });

  it('shows what was recorded, as plain counts', async () => {
    await open();
    const counts = screen.getByRole('heading', { level: 2, name: 'ما سجّلته' }).closest('section');
    expect(counts).toHaveTextContent('أسئلة سألتها');
    expect(counts).toHaveTextContent('5');
  });
});

describe('questEntries', () => {
  it('marks the first undone step current and the later ones pending', () => {
    const steps = [
      { id: 'a', label: 'أ', done: false },
      { id: 'b', label: 'ب', done: false },
    ];
    expect(questEntries(steps).map((entry) => entry.state)).toEqual(['current', 'pending']);
  });
});

describe('the sky of meanings on the page', () => {
  it('leads the page, with the page name above its heading', async () => {
    await open();
    const h1 = screen.getByRole('heading', { level: 1, name: 'تمرينك' });
    const sky = screen.getByRole('region', { name: 'سماء المعاني' });
    expect(sky).toContainElement(h1);
    expect(screen.getByRole('button', { name: '[معنى ثان]، بصيرتان مرتبطتان' })).toBeVisible();
  });

  it('reads the record again when the page comes back into view, keeping the stars meanwhile', async () => {
    let calls = 0;
    let answer: (value: { body: typeof PROGRESS }) => void = () => undefined;
    mockApi({
      'GET /me/progress': () => {
        calls += 1;
        return calls === 1
          ? { body: PROGRESS }
          : new Promise((resolve) => {
              answer = resolve;
            });
      },
    });
    screenInShell();
    await screen.findByRole('button', { name: /^\[معنى ثان\]/ });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(calls).toBe(2));
    expect(screen.getByRole('region', { name: 'سماء المعاني' })).toHaveAttribute(
      'aria-busy',
      'true'
    );
    expect(screen.getByRole('button', { name: /^\[معنى ثان\]/ })).toBeInTheDocument();
    const learned = {
      concept: '[معنى ثالث]',
      count: 1,
      first_seen: '2026-10-04T08:00:00Z',
      x: 0.5,
      y: 0.2,
      insights: [{ id: '104', title: '[بصيرة رابعة]', completed_at: '2026-10-04T08:00:00Z' }],
    };
    act(() => {
      answer({ body: { ...PROGRESS, sky: { count: 3, stars: [...PROGRESS.sky.stars, learned] } } });
    });
    expect(await screen.findByRole('button', { name: /^\[معنى ثالث\]/ })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'سماء المعاني' })).toHaveAttribute(
      'aria-busy',
      'false'
    );
  });

  it('keeps the stars when a quiet reload fails: a network failure is not an empty sky', async () => {
    let calls = 0;
    mockApi({
      'GET /me/progress': () => {
        calls += 1;
        return calls === 1 ? { body: PROGRESS } : apiError(500, 'internal_error');
      },
    });
    screenInShell();
    await screen.findByRole('button', { name: /^\[معنى ثان\]/ });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(calls).toBe(2));
    await waitFor(() =>
      expect(screen.getByRole('region', { name: 'سماء المعاني' })).toHaveAttribute(
        'aria-busy',
        'false'
      )
    );
    expect(screen.getByRole('button', { name: /^\[معنى ثان\]/ })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('stays on its failure when a quiet reload fails too, and recovers when one succeeds', async () => {
    let calls = 0;
    mockApi({
      'GET /me/progress': () => {
        calls += 1;
        return calls < 3 ? apiError(500, 'internal_error') : { body: PROGRESS };
      },
    });
    screenInShell();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(calls).toBe(2));
    expect(screen.getByRole('alert')).toBeInTheDocument();
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(await screen.findByRole('button', { name: /^\[معنى ثان\]/ })).toBeInTheDocument();
  });

  it('does not read the record again while the page is hidden', async () => {
    let calls = 0;
    mockApi({
      'GET /me/progress': () => {
        calls += 1;
        return { body: PROGRESS };
      },
    });
    screenInShell();
    await screen.findByRole('button', { name: /^\[معنى ثان\]/ });
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(calls).toBe(1);
    vi.restoreAllMocks();
  });

  it('says one meaning in the singular', async () => {
    await open({ ...PROGRESS, sky: { count: 1, stars: PROGRESS.sky.stars.slice(0, 1) } });
    expect(screen.getByText('معنى أضاء لك')).toBeInTheDocument();
  });
});

describe('reloads that overlap', () => {
  it('keeps the newest answer when an older one arrives after it', async () => {
    const answers: Array<(value: { body: typeof PROGRESS }) => void> = [];
    mockApi({
      'GET /me/progress': () =>
        new Promise((resolve) => {
          answers.push(resolve);
        }),
    });
    screenInShell();
    await waitFor(() => expect(answers).toHaveLength(1));
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(answers).toHaveLength(2));
    const newer = { ...PROGRESS, sky: { count: 1, stars: PROGRESS.sky.stars.slice(0, 1) } };
    act(() => answers[1]?.({ body: newer }));
    expect(await screen.findByText('معنى أضاء لك')).toBeInTheDocument();
    act(() => answers[0]?.({ body: PROGRESS }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText('معنى أضاء لك')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^\[معنى ثان\]/ })).toBeNull();
  });
});

describe('the badges', () => {
  it('shows earned badges with their day and locked ones with their rule', async () => {
    await open();
    expect(screen.getByText('1 من 2')).toBeInTheDocument();
    const earned = screen.getByText('[علامة نالها]').closest('li');
    const locked = screen.getByText('[علامة مقفلة]').closest('li');
    expect(earned).toHaveAttribute('data-earned', 'true');
    expect(earned).toHaveTextContent('نلتها');
    expect(earned).toHaveTextContent('2026');
    expect(locked).toHaveAttribute('data-earned', 'false');
    expect(locked).toHaveTextContent('لم تُنل بعد');
    expect(locked).toHaveTextContent('[وصف علامة مقفلة]');
    expect(locked).not.toHaveTextContent('2026');
  });
});
