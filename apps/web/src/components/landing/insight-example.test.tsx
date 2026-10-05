import { createHash } from 'node:crypto';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readSession, setSignedIn } from '@/account/session';
import { apiError, mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { insightOut, tutorialOut } from '@/test/scan';
import { InsightExample } from './insight-example';

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router }));

beforeEach(() => {
  router.push.mockClear();
});

const sha256 = (text: string) => createHash('sha256').update(text, 'utf8').digest('hex');

describe('InsightExample', () => {
  it('shows the whole pair of the first insight byte for byte, apart from its reflection', async () => {
    const tutorial = tutorialOut();
    const drop = tutorial.insights[0] as (typeof tutorial.insights)[number];
    mockApi({ 'GET /tutorial/rain': { body: tutorial } });
    const { container } = render(<InsightExample />);

    expect(screen.getByRole('status')).toHaveTextContent('نحضّر المثال…');
    const panel = await screen.findByRole('tabpanel', { name: 'الحياة في قطرة' });
    const verse = container.querySelector('[data-scripture="quran"]')?.textContent as string;
    const hadith = container.querySelector('[data-scripture="hadith"]')?.textContent as string;
    expect(sha256(verse)).toBe(drop.quran.verse.sha256);
    expect(sha256(hadith)).toBe(drop.hadith?.hadith.sha256);
    expect(within(panel).getByText('مثال موثّق مُعدّ')).toBeInTheDocument();
    const reflection = within(panel).getByRole('region', { name: 'التأمّل' });
    expect(reflection).toHaveTextContent('كيف تُحيا الأرض');
    // The step is the API's, under its own label: it may rest on either text, both shown.
    // The small step under the API's own label, as a quest of its own below the reflection.
    expect(within(reflection).getByText(drop.small_step?.label as string)).toBeInTheDocument();
    expect(within(reflection).getByText(drop.small_step?.text as string)).toBeInTheDocument();
    expect(reflection).toHaveTextContent('خذ لحظة، واقرأ على مهل.');
  });

  it('moves between its tabs with the arrows, and says why a hadith still waits', async () => {
    mockApi({ 'GET /tutorial/rain': { body: tutorialOut() } });
    render(<InsightExample />);
    await screen.findByRole('tabpanel');
    const drop = screen.getByRole('tab', { name: 'الحياة في قطرة' });
    expect(drop).toHaveAttribute('aria-selected', 'true');

    drop.focus();
    await userEvent.keyboard('{ArrowLeft}');

    const planting = screen.getByRole('tab', { name: 'الغرس الذي يتعدّاك' });
    expect(planting).toHaveFocus();
    expect(planting).toHaveAttribute('aria-selected', 'true');
    const panel = screen.getByRole('tabpanel', { name: 'الغرس الذي يتعدّاك' });
    expect(within(panel).getByRole('heading', { name: 'الغرس الذي يتعدّاك' })).toBeInTheDocument();
    expect(panel.querySelector('[data-scripture="hadith"]')).toBeNull();
    await userEvent.keyboard('{ArrowRight}');
    expect(drop).toHaveFocus();
    await userEvent.keyboard('{End}');
    expect(planting).toHaveFocus();
    await userEvent.keyboard('{Home}');
    expect(drop).toHaveFocus();
    await userEvent.keyboard('a');
    expect(drop).toHaveFocus();
  });

  it('shows the hadith of the second insight when the API shows it', async () => {
    const tutorial = tutorialOut();
    const drop = tutorial.insights[0] as (typeof tutorial.insights)[number];
    const planting = tutorial.insights[1] as (typeof tutorial.insights)[number];
    tutorial.insights[1] = {
      ...planting,
      hadith: drop.hadith,
      hadith_status: 'shown',
    };
    mockApi({ 'GET /tutorial/rain': { body: tutorial } });
    render(<InsightExample />);
    await screen.findByRole('tabpanel');

    await userEvent.click(screen.getByRole('tab', { name: 'الغرس الذي يتعدّاك' }));

    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getByText(/صحيح اختبار/)).toBeInTheDocument();
    const hadith = panel.querySelector('[data-scripture="hadith"]')?.textContent as string;
    expect(sha256(hadith)).toBe(drop.hadith?.hadith.sha256);
  });

  it('opens the insight of the tab it shows', async () => {
    const api = mockApi({
      'GET /tutorial/rain': { body: tutorialOut() },
      'POST /tutorial/rain/insights/planting': {
        status: 201,
        body: insightOut({ id: '110000000000000077' }),
      },
    });
    render(<InsightExample />);
    await screen.findByRole('tabpanel');
    await userEvent.click(screen.getByRole('tab', { name: 'الغرس الذي يتعدّاك' }));

    await userEvent.click(screen.getByRole('button', { name: 'افتح البصيرة' }));

    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/insight/110000000000000077'));
    expect(api.requests.map((request) => new URL(request.url).pathname)).toContain(
      '/tutorial/rain/insights/planting'
    );
  });

  it('says when the insight could not be opened, and when the example could not load', async () => {
    let calls = 0;
    mockApi({
      'GET /tutorial/rain': () => {
        calls += 1;
        return calls === 1 ? apiError(503, 'service_unavailable') : { body: tutorialOut() };
      },
      'POST /tutorial/rain/insights/drop': apiError(503, 'service_unavailable'),
    });
    render(<InsightExample />);

    expect(await screen.findByRole('alert')).toHaveTextContent('تعذّر تحميل المثال');
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    await screen.findByRole('heading', { name: 'الحياة في قطرة' });
    await userEvent.click(screen.getByRole('button', { name: 'افتح البصيرة' }));

    expect(await screen.findByText(/تعذّر|حاول/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'افتح البصيرة' })).toBeEnabled();
    expect(router.push).not.toHaveBeenCalled();
  });

  it('gives way to the capture when the account holds an insight of its own', async () => {
    setSignedIn(USER);
    mockApi({
      'GET /tutorial/rain': { body: tutorialOut() },
      'POST /tutorial/rain/insights/drop': apiError(403, 'tutorial_closed'),
    });
    render(<InsightExample />);
    await screen.findByRole('heading', { name: 'الحياة في قطرة' });

    await userEvent.click(screen.getByRole('button', { name: 'افتح البصيرة' }));

    await waitFor(() => expect(readSession()).toMatchObject({ user: { has_own_insight: true } }));
    expect(router.push).not.toHaveBeenCalled();
  });
});

describe('InsightExample, leaving early', () => {
  it('drops an answer that arrives after the page left', async () => {
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
    const { unmount } = render(<InsightExample />);
    unmount();
    answer(
      new Response(JSON.stringify(tutorialOut()), {
        headers: { 'Content-Type': 'application/json' },
      })
    );
    await Promise.resolve();
    expect(screen.queryByRole('tabpanel')).toBeNull();
  });
});
