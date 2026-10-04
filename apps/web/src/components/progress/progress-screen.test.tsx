import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { messages } from '@/messages';
import { apiError, mockApi } from '@/test/api';
import { PROGRESS, PROGRESS_COMPLETE, PROGRESS_EMPTY } from '@/test/world';
import { ProgressScreen } from './progress-screen';
import { questEntries } from './quest-card';

async function open(body = PROGRESS) {
  const api = mockApi({ 'GET /me/progress': { body } });
  render(<ProgressScreen />);
  await screen.findByRole('heading', { level: 2, name: body.rank.title });
  return api;
}

describe('ProgressScreen states', () => {
  it('says it is loading, and always offers the way back to «ملفي»', () => {
    mockApi({});
    render(<ProgressScreen />);
    expect(screen.getByRole('status')).toHaveTextContent('نحمّل تمرينك…');
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
    render(<ProgressScreen />);
    expect(await screen.findByRole('alert')).toHaveTextContent('تعذّر تحميل تمرينك الآن');
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

describe('the sky of meanings', () => {
  it('draws a star for each meaning and names it on a press, never on hover', async () => {
    await open();
    const first = screen.getByRole('button', { name: '[معنى أول]، مرة واحدة' });
    const second = screen.getByRole('button', { name: '[معنى ثان]، 4 مرات' });
    expect(screen.getByText('2 معاني أضاءت لك')).toBeInTheDocument();
    expect(first).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(second);
    expect(second).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('[معنى ثان]، 4 مرات', { selector: 'p' })).toBeInTheDocument();
    await userEvent.click(first);
    expect(second).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(first);
    expect(first).toHaveAttribute('aria-pressed', 'false');
  });

  it('keeps a star where its name puts it', async () => {
    await open();
    const star = screen.getByRole('button', { name: '[معنى أول]، مرة واحدة' });
    expect(star.style.left).toBe('20%');
    expect(star.style.top).toBe('30%');
  });

  it('invites to a first scene while the sky is empty', async () => {
    await open(PROGRESS_EMPTY);
    expect(screen.getByText(/لم يُضئ معنى بعد/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'ابدأ بأول مشهد' })).toHaveAttribute('href', '/');
    expect(screen.getByText('لا معنى بعد')).toBeInTheDocument();
  });

  it('says one meaning in the singular', async () => {
    await open({ ...PROGRESS, sky: { count: 1, stars: PROGRESS.sky.stars.slice(0, 1) } });
    expect(screen.getByText('معنى أضاء لك')).toBeInTheDocument();
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
