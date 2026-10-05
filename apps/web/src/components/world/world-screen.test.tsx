import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CaptureProvider } from '@/components/capture/capture-provider';
import { setAmbientMotion } from '@/preferences/motion';
import { apiError, mockApi, type Route } from '@/test/api';
import { stubMatchMedia } from '@/test/media';
import { insightOut } from '@/test/scan';
import {
  PLACE_ONE,
  PLACE_TWO,
  REVEALS,
  WORLD,
  WORLD_JUST_LEARNED,
  WORLD_UNDER_FOG,
} from '@/test/world';
import type { Place, Reveal } from '@/world/api';
import { WorldScreen } from './world-screen';

const router = vi.hoisted(() => ({ push: vi.fn(), back: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router, usePathname: () => '/world' }));
vi.mock('./world-pictures', () => ({
  LANDSCAPE_SRC: '/world/landscape-1.webp',
  CLOUDS_SRC: '/world/clouds-1.webp',
  loadPicture: () => Promise.resolve({}),
}));

function fakeContext() {
  const gradient = { addColorStop: vi.fn() };
  return {
    clearRect: vi.fn(),
    drawImage: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    createRadialGradient: vi.fn(() => gradient),
    createLinearGradient: vi.fn(() => gradient),
  };
}

beforeEach(() => {
  router.push.mockClear();
  router.back.mockClear();
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(1440);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(828);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    () => fakeContext() as unknown as RenderingContext
  );
});

afterEach(() => {
  setAmbientMotion(true);
});

function open(routes: Record<string, Route>) {
  const api = mockApi(routes);
  render(
    <CaptureProvider>
      <WorldScreen />
    </CaptureProvider>
  );
  return api;
}

const phase = () => document.querySelector('[data-phase]')?.getAttribute('data-phase');

describe('WorldScreen', () => {
  it('shows clouds only while it loads: never an empty world that is not one', () => {
    open({ 'GET /world': () => new Promise(() => undefined) });

    expect(screen.getByRole('status')).toHaveTextContent('نفتح عالمك…');
    expect(screen.getByRole('heading', { level: 1, name: 'عالمي' })).toBeInTheDocument();
    expect(screen.queryByText('كلّ بصيرة تفتح أفقًا.')).toBeNull();
    expect(screen.queryByRole('button', { name: /اكتشف/ })).toBeNull();
    expect(phase()).toBe('loading');
  });

  it('keeps the clouds and offers a retry when the world cannot be read', async () => {
    let calls = 0;
    open({
      'GET /world': () => {
        calls += 1;
        return calls === 1 ? apiError(503, 'service_unavailable') : { body: WORLD_UNDER_FOG };
      },
    });

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('ما تعلّمته محفوظ كما هو');
    expect(phase()).toBe('unavailable');
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));

    expect(await screen.findByText('كلّ بصيرة تفتح أفقًا.')).toBeInTheDocument();
  });

  it('greets a newcomer with clouds, one invitation and the camera: no names, list or count', async () => {
    open({ 'GET /world': { body: WORLD_UNDER_FOG } });

    await screen.findByText('كلّ بصيرة تفتح أفقًا.');
    expect(phase()).toBe('ready-empty');
    expect(screen.queryByRole('button', { name: 'بصائري' })).toBeNull();
    for (const name of ['[منطقة أولى]', '[منطقة ثالثة]', '[موضع أول]']) {
      expect(screen.queryByText(name)).toBeNull();
    }
    expect(screen.queryByRole('list')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: /اكتشف أول بصيرة/ }));
    expect(await screen.findByRole('dialog', { name: 'صوّر مشهدًا' })).toBeInTheDocument();
  });

  it('lists what was learned in «بصائري» and opens one at its place, with its sources', async () => {
    const second = insightOut({
      id: '9002',
      title: '[بصيرة ثانية]',
      completed_at: '2026-10-02T08:00:00Z',
    });
    const api = open({
      'GET /world': { body: WORLD },
      'GET /insights/9002': { body: second },
      'POST /world/places/7002/visit': { body: PLACE_TWO },
    });

    await userEvent.click(await screen.findByRole('button', { name: 'بصائري' }));
    const list = screen.getByRole('dialog', { name: 'بصائري' });
    const titles = within(list)
      .getAllByRole('button')
      .map((button) => button.textContent);
    expect(titles.slice(1)).toEqual([
      expect.stringContaining('[بصيرة ثالثة]'),
      expect.stringContaining('[بصيرة ثانية]'),
      expect.stringContaining('[بصيرة أولى]'),
    ]);
    await userEvent.click(within(list).getByRole('button', { name: /\[بصيرة ثانية\]/ }));

    const panel = screen.getByRole('dialog', { name: PLACE_TWO.name });
    expect(
      await within(panel).findByRole('heading', { level: 3, name: '[بصيرة ثانية]' })
    ).toBeInTheDocument();
    expect(within(panel).getByText('بصيرة متعلّمة')).toBeInTheDocument();
    expect(within(panel).getByText(second.glimpse)).toBeInTheDocument();
    expect(within(panel).getByText('سورة اختبار · 50')).toBeInTheDocument();
    expect(within(panel).getByText('صحيح اختبار · 1032')).toBeInTheDocument();
    expect(within(panel).queryByText(/الدرر/)).toBeNull();
    expect(within(panel).getByText('احفظ الدعاء الوارد في الحديث.')).toBeInTheDocument();
    expect(within(panel).getByRole('link', { name: 'افتح البصيرة' })).toHaveAttribute(
      'href',
      '/insight/9002'
    );
    expect(within(panel).getByRole('link', { name: 'حاور بصيرتك' })).toBeInTheDocument();
    await waitFor(() =>
      expect(api.requests.map((request) => new URL(request.url).pathname)).toContain(
        '/world/places/7002/visit'
      )
    );
    // The scripture text itself stays on the insight's own screen.
    expect(within(panel).queryByText(second.quran?.verse.text as string)).toBeNull();

    await userEvent.click(within(panel).getByRole('button', { name: 'انتقل إلى موضعها' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens a landmark on its latest insight, with the others learned there', async () => {
    const answer = (id: string, title: string) => ({
      body: insightOut({ id, title, completed_at: '2026-10-02T09:00:00Z', small_step: null }),
    });
    open({
      'GET /world': { body: WORLD },
      'GET /insights/9003': answer('9003', '[بصيرة ثالثة]'),
      'GET /insights/9002': answer('9002', '[بصيرة ثانية]'),
      'POST /world/places/7002/visit': { body: { ...PLACE_TWO, treasure: null } },
    });

    await userEvent.click(
      await screen.findByRole('button', { name: `افتح ما تعلّمته في ${PLACE_TWO.name}: بصيرتان` })
    );
    const panel = screen.getByRole('dialog', { name: PLACE_TWO.name });
    expect(
      await within(panel).findByRole('heading', { level: 3, name: '[بصيرة ثالثة]' })
    ).toBeInTheDocument();
    const others = within(panel).getByRole('region', { name: 'بصائر أخرى في هذا الموضع' });
    await userEvent.click(within(others).getByRole('button', { name: /\[بصيرة ثانية\]/ }));
    expect(
      await within(panel).findByRole('heading', { level: 3, name: '[بصيرة ثانية]' })
    ).toBeInTheDocument();
  });

  it('says when an insight cannot be read, and reads it again on request', async () => {
    let calls = 0;
    open({
      'GET /world': { body: WORLD },
      'GET /insights/9001': () => {
        calls += 1;
        return calls === 1
          ? apiError(503, 'service_unavailable')
          : { body: insightOut({ id: '9001', title: '[بصيرة أولى]', quran: null, hadith: null }) };
      },
      'POST /world/places/7001/visit': { body: PLACE_ONE },
    });

    await userEvent.click(
      await screen.findByRole('button', { name: 'افتح البصيرة المتعلّمة: [بصيرة أولى]' })
    );
    const panel = screen.getByRole('dialog', { name: PLACE_ONE.name });
    expect(await within(panel).findByRole('alert')).toHaveTextContent('تعذّر تحميل');
    await userEvent.click(within(panel).getByRole('button', { name: 'أعد المحاولة' }));
    expect(
      await within(panel).findByRole('heading', { level: 3, name: '[بصيرة أولى]' })
    ).toBeInTheDocument();
    expect(within(panel).queryByRole('region', { name: 'المصدر' })).toBeNull();
  });

  it('explains itself on request only, with the site pages, and gives focus back', async () => {
    open({ 'GET /world': { body: WORLD } });
    const help = await screen.findByRole('button', { name: 'كيف يعمل عالمي؟' });
    expect(screen.queryByRole('dialog')).toBeNull();

    await userEvent.click(help);
    const panel = screen.getByRole('dialog', { name: 'كيف يعمل عالمي؟' });
    expect(within(panel).getByRole('link', { name: 'سياسة الخصوصية' })).toHaveAttribute(
      'href',
      '/privacy'
    );
    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(help).toHaveFocus();
  });

  it('closes its help before the cookie choice opens', async () => {
    open({ 'GET /world': { body: WORLD } });
    await userEvent.click(await screen.findByRole('button', { name: 'كيف يعمل عالمي؟' }));
    await userEvent.click(screen.getByRole('button', { name: 'إعدادات ملفات تعريف الارتباط' }));
    expect(screen.queryByRole('dialog', { name: 'كيف يعمل عالمي؟' })).toBeNull();
  });

  it('announces a reveal it shows for the first time, and tells the API once', async () => {
    setAmbientMotion(false);
    const api = open({
      'GET /world': { body: WORLD_JUST_LEARNED },
      'POST /world/reveals/shown': { status: 204 },
    });

    await waitFor(() =>
      expect(screen.getByText('حُفظت بصيرتك، وانكشف [موضع أول].')).toBeInTheDocument()
    );
    expect(await api.bodies('POST', '/world/reveals/shown')).toEqual([{ ids: ['6001'] }]);
    expect(phase()).toBe('ready-progress');
  });

  it('says a region widened when only a widening was learned', async () => {
    setAmbientMotion(false);
    const widening = { ...(REVEALS[2] as Reveal), shown: false };
    open({
      'GET /world': { body: { ...WORLD, reveals: [REVEALS[0], REVEALS[1], widening] } },
      'POST /world/reveals/shown': { status: 204 },
    });

    expect(await screen.findByText(`حُفظت بصيرتك، واتّسع ${PLACE_TWO.name}.`)).toBeInTheDocument();
  });

  it('reads the world again when the page comes back, keeping what it played', async () => {
    let calls = 0;
    open({
      'GET /world': () => {
        calls += 1;
        return calls === 1 ? { body: WORLD_UNDER_FOG } : { body: WORLD };
      },
    });
    await screen.findByText('كلّ بصيرة تفتح أفقًا.');

    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(await screen.findByRole('button', { name: 'بصائري' })).toBeInTheDocument();
  });

  it('goes back where the reader came from, or home', async () => {
    open({ 'GET /world': { body: WORLD } });
    await screen.findByRole('button', { name: 'بصائري' });
    const back = screen.getByRole('button', { name: 'رجوع' });
    vi.spyOn(History.prototype, 'length', 'get').mockReturnValue(3);
    await userEvent.click(back);
    expect(router.back).toHaveBeenCalledOnce();
    vi.spyOn(History.prototype, 'length', 'get').mockReturnValue(1);
    await userEvent.click(back);
    expect(router.push).toHaveBeenCalledWith('/');
  });
});

describe('WorldScreen, the edges', () => {
  it('flies a spot picked in «بصائري» beside the side panel from tablet up', async () => {
    stubMatchMedia((query) => query.includes('min-width'));
    open({
      'GET /world': { body: WORLD },
      'GET /insights/9001': { body: insightOut({ id: '9001', title: '[بصيرة أولى]' }) },
      'POST /world/places/7001/visit': apiError(503, 'service_unavailable'),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'بصائري' }));
    await userEvent.click(
      within(screen.getByRole('dialog', { name: 'بصائري' })).getByRole('button', {
        name: /\[بصيرة أولى\]/,
      })
    );

    const panel = screen.getByRole('dialog', { name: PLACE_ONE.name });
    expect(
      await within(panel).findByRole('heading', { level: 3, name: '[بصيرة أولى]' })
    ).toBeInTheDocument();
    // A visit that could not be recorded changes nothing on screen.
    expect(within(panel).queryByText('كنز مخبوء')).toBeNull();
  });

  it('keeps an insight with no spot on the picture in «بصائري», and goes nowhere for it', async () => {
    const lone = {
      ...PLACE_ONE,
      id: '7009',
      insights: [{ ...(PLACE_ONE.insights[0] as Place['insights'][number]), reveal_id: null }],
    };
    open({
      'GET /world': { body: { ...WORLD, places: [lone], reveals: [] } },
      'GET /insights/9001': { body: insightOut({ id: '9001', title: '[بصيرة أولى]' }) },
      'POST /world/places/7009/visit': { body: lone },
    });
    await userEvent.click(await screen.findByRole('button', { name: 'بصائري' }));
    await userEvent.click(
      within(screen.getByRole('dialog', { name: 'بصائري' })).getByRole('button', {
        name: /\[بصيرة أولى\]/,
      })
    );
    const panel = screen.getByRole('dialog', { name: PLACE_ONE.name });
    await within(panel).findByRole('heading', { level: 3, name: '[بصيرة أولى]' });

    await userEvent.click(within(panel).getByRole('button', { name: 'انتقل إلى موضعها' }));

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('button', { name: /افتح البصيرة المتعلّمة/ })).toBeNull();
  });

  it('goes to a reveal learned in another tab when the page comes back', async () => {
    setAmbientMotion(false);
    let calls = 0;
    open({
      'GET /world': () => {
        calls += 1;
        return { body: calls === 1 ? { ...WORLD, reveals: [REVEALS[1]] } : WORLD_JUST_LEARNED };
      },
      'POST /world/reveals/shown': { status: 204 },
    });
    await screen.findByRole('button', { name: 'بصائري' });

    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(await screen.findByText('حُفظت بصيرتك، وانكشف [موضع أول].')).toBeInTheDocument();
  });
});

describe('WorldScreen, an empty place', () => {
  it('opens a landmark whose place lists nothing yet without asking for an insight', async () => {
    const bare = { ...PLACE_ONE, insights: [] };
    open({
      'GET /world': { body: { ...WORLD, places: [bare, PLACE_TWO] } },
      'POST /world/places/7001/visit': { body: bare },
    });

    await userEvent.click(
      await screen.findByRole('button', { name: `افتح البصيرة المتعلّمة: ${PLACE_ONE.name}` })
    );

    const panel = screen.getByRole('dialog', { name: PLACE_ONE.name });
    expect(within(panel).queryByRole('article')).toBeNull();
    expect(within(panel).queryByRole('status')).toBeNull();
  });
});

describe('WorldScreen, after a quiet reload', () => {
  it('closes a panel whose insight or place a reload took away', async () => {
    let calls = 0;
    const later = { ...PLACE_TWO, insights: PLACE_TWO.insights.slice(1) };
    open({
      'GET /world': () => {
        calls += 1;
        if (calls === 1) {
          return { body: WORLD };
        }
        return {
          body:
            calls === 2
              ? { ...WORLD, places: [PLACE_ONE, later] }
              : { ...WORLD, places: [PLACE_ONE] },
        };
      },
      'GET /insights/9002': { body: insightOut({ id: '9002', title: '[بصيرة ثانية]' }) },
      'POST /world/places/7002/visit': { body: PLACE_TWO },
    });
    await userEvent.click(await screen.findByRole('button', { name: 'بصائري' }));
    await userEvent.click(
      within(screen.getByRole('dialog', { name: 'بصائري' })).getByRole('button', {
        name: /\[بصيرة ثانية\]/,
      })
    );
    const panel = screen.getByRole('dialog', { name: PLACE_TWO.name });
    await within(panel).findByRole('heading', { level: 3, name: '[بصيرة ثانية]' });

    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(calls).toBe(2));
    await userEvent.click(within(panel).getByRole('button', { name: 'انتقل إلى موضعها' }));
    expect(screen.queryByRole('dialog')).toBeNull();

    await userEvent.click(
      screen.getByRole('button', { name: `افتح البصيرة المتعلّمة: ${PLACE_TWO.insights[1]?.title}` })
    );
    expect(screen.getByRole('dialog', { name: PLACE_TWO.name })).toBeInTheDocument();
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('names a landmark by its region when its place is not in the answer', async () => {
    open({ 'GET /world': { body: { ...WORLD, places: [], reveals: [REVEALS[0]] } } });

    expect(
      await screen.findByRole('button', { name: 'افتح البصيرة المتعلّمة: [منطقة أولى]' })
    ).toBeInTheDocument();
  });
});

describe('WorldScreen, a widening alone', () => {
  it('flies to an insight whose region shows no landmark, and focuses nothing it cannot find', async () => {
    const third = PLACE_TWO.insights[1] as Place['insights'][number];
    const place = { ...PLACE_TWO, insights: [third] };
    open({
      'GET /world': { body: { ...WORLD, places: [place], reveals: [REVEALS[2]] } },
      'GET /insights/9003': { body: insightOut({ id: '9003', title: third.title }) },
      'POST /world/places/7002/visit': { body: place },
    });
    await userEvent.click(await screen.findByRole('button', { name: 'بصائري' }));
    await userEvent.click(
      within(screen.getByRole('dialog', { name: 'بصائري' })).getByRole('button', {
        name: new RegExp(third.title.replace(/[[\]]/g, '.')),
      })
    );
    const panel = screen.getByRole('dialog', { name: PLACE_TWO.name });
    await within(panel).findByRole('heading', { level: 3, name: third.title });

    await userEvent.click(within(panel).getByRole('button', { name: 'انتقل إلى موضعها' }));
    await act(async () => {
      await new Promise((resolve) => requestAnimationFrame(resolve));
    });

    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
