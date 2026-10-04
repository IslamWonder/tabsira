import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CLARITY_SCRIPT_ID } from '@/analytics/clarity';
import { GA_SCRIPT_ID } from '@/analytics/google';
import { decide, initConsent } from '@/consent/store';
import { mockApi } from '@/test/api';
import { POLICY, RECORD } from '@/test/fixtures';
import { AnalyticsTags } from './analytics-tags';

const where = vi.hoisted(() => ({ pathname: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => where.pathname }));

const gtag = vi.fn();
const GA = 'G-TEST1234';
const CLARITY = 'abc123xyz9';
const GA_URL = `https://www.googletagmanager.com/gtag/js?id=${GA}`;
const CLARITY_URL = `https://www.clarity.ms/tag/${CLARITY}`;
const flag = () => (window as unknown as Record<string, unknown>)[`ga-disable-${GA}`];

function scriptSources(): string[] {
  return Array.from(document.querySelectorAll('script[src]')).map(
    (script) => script.getAttribute('src') ?? ''
  );
}

/** What the API will record next; one mock for the whole test, installed before the page renders. */
const chosen = { analytics: false, behaviour: false };
let api: ReturnType<typeof mockApi>;

function answers() {
  return mockApi({
    'GET /consent/policy': { body: POLICY },
    'POST /consent': () => ({ body: { ...RECORD, categories: { necessary: true, ...chosen } } }),
  });
}

async function choose(analytics: boolean, behaviour: boolean) {
  chosen.analytics = analytics;
  chosen.behaviour = behaviour;
  await act(async () => {
    await decide({ necessary: true, analytics, behaviour });
  });
}

beforeEach(() => {
  gtag.mockClear();
  vi.stubGlobal('gtag', gtag);
  where.pathname = '/';
  api = answers();
});

afterEach(() => {
  document.getElementById(GA_SCRIPT_ID)?.remove();
  document.getElementById(CLARITY_SCRIPT_ID)?.remove();
  Reflect.deleteProperty(window, 'clarity');
  Reflect.deleteProperty(window, `ga-disable-${GA}`);
});

describe('before any consent', () => {
  it('adds no analytics script and makes no request to Google or Microsoft, on a first visit', async () => {
    render(<AnalyticsTags gaId={GA} clarityId={CLARITY} />);
    await act(async () => {
      initConsent();
    });
    expect(scriptSources()).toEqual([]);
    expect(document.documentElement.outerHTML).not.toMatch(
      /googletagmanager|google-analytics|clarity\.ms/
    );
    expect(gtag).not.toHaveBeenCalled();
    const hosts = api.requests.map((request) => new URL(request.url).host);
    expect(hosts.filter((host) => /google|clarity|microsoft/.test(host))).toEqual([]);
  });

  it('adds nothing after a refusal of everything', async () => {
    render(<AnalyticsTags gaId={GA} clarityId={CLARITY} />);
    await choose(false, false);
    expect(scriptSources()).toEqual([]);
    expect(gtag).not.toHaveBeenCalledWith('event', expect.anything(), expect.anything());
  });

  it('adds nothing when no id is configured, even after accepting everything', async () => {
    render(<AnalyticsTags gaId={null} clarityId={null} />);
    await choose(true, true);
    expect(scriptSources()).toEqual([]);
  });
});

describe('after consent', () => {
  it('loads Google only for the analytics category and Clarity only for the behaviour category', async () => {
    render(<AnalyticsTags gaId={GA} clarityId={CLARITY} />);
    await choose(true, false);
    expect(scriptSources()).toEqual([GA_URL]);
    await choose(true, true);
    expect(scriptSources()).toEqual([GA_URL, CLARITY_URL]);
  });

  it('reports a change of the choice, but not the same choice again', async () => {
    render(<AnalyticsTags gaId={GA} clarityId={null} />);
    await choose(true, false);
    expect(gtag).toHaveBeenCalledWith('event', 'consent_changed', {
      analytics: true,
      behaviour: false,
    });
    gtag.mockClear();
    await choose(true, false);
    expect(gtag).not.toHaveBeenCalledWith('event', 'consent_changed', expect.anything());
    await choose(true, true);
    expect(gtag).toHaveBeenCalledWith('event', 'consent_changed', {
      analytics: true,
      behaviour: true,
    });
  });

  it('does not report the choice found already in force at a later visit', async () => {
    mockApi({
      [`GET /consent/${RECORD.consent_id}`]: { body: RECORD },
      'GET /consent/policy': { body: POLICY },
    });
    // biome-ignore lint/suspicious/noDocumentCookie: the cookie of an earlier visit.
    document.cookie = `tabsira_consent=${RECORD.consent_id}; Path=/`;
    render(<AnalyticsTags gaId={GA} clarityId={null} />);
    await vi.waitFor(() => expect(scriptSources()).toEqual([GA_URL]));
    expect(gtag).not.toHaveBeenCalledWith('event', 'consent_changed', expect.anything());
  });

  it('stops both tools and deletes their cookies on withdrawal', async () => {
    render(<AnalyticsTags gaId={GA} clarityId={CLARITY} />);
    await choose(true, true);
    // biome-ignore lint/suspicious/noDocumentCookie: what the tools would have written.
    document.cookie = '_ga=GA1.1.1; Path=/';
    // biome-ignore lint/suspicious/noDocumentCookie: what the tools would have written.
    document.cookie = '_clck=1; Path=/';
    await choose(false, false);
    expect(gtag).toHaveBeenCalledWith('consent', 'update', { analytics_storage: 'denied' });
    expect(document.cookie).not.toMatch(/_ga|_clck/);
    const clarity = (window as unknown as { clarity: { q: unknown[][] } }).clarity.q;
    expect(clarity.at(-1)).toEqual(['stop']);
  });

  it('is paused on sign-in and account pages and resumes elsewhere', async () => {
    where.pathname = '/signin';
    const { rerender } = render(<AnalyticsTags gaId={GA} clarityId={CLARITY} />);
    await choose(true, true);
    expect(flag()).toBe(true);
    expect(document.getElementById(CLARITY_SCRIPT_ID)).toBeNull();
    where.pathname = '/world';
    rerender(<AnalyticsTags gaId={GA} clarityId={CLARITY} />);
    expect(flag()).toBe(false);
    expect(document.getElementById(CLARITY_SCRIPT_ID)).not.toBeNull();
    where.pathname = '/me';
    rerender(<AnalyticsTags gaId={GA} clarityId={CLARITY} />);
    expect(flag()).toBe(true);
  });

  it('sends a fixed page title on a public insight, before the first page view and on each path change', async () => {
    where.pathname = '/insights/123';
    document.title = 'عنوان بصيرة | تبصرة';
    const { rerender } = render(<AnalyticsTags gaId={GA} clarityId={CLARITY} />);
    await choose(true, true);
    const titles = () =>
      gtag.mock.calls.filter(([command]) => command === 'set').map(([, value]) => value);
    expect(titles()).toEqual([{ page_title: '/insights/[id]' }, { page_title: '/insights/[id]' }]);
    const order = gtag.mock.calls.map(([command]) => command);
    expect(order.indexOf('set')).toBeLessThan(order.indexOf('config'));
    expect(JSON.stringify(gtag.mock.calls)).not.toContain('عنوان بصيرة');
    where.pathname = '/world';
    rerender(<AnalyticsTags gaId={GA} clarityId={CLARITY} />);
    expect(titles().at(-1)).toEqual({ page_title: undefined });
  });

  it('runs no heatmap on a public insight', async () => {
    where.pathname = '/insights/123';
    render(<AnalyticsTags gaId={GA} clarityId={CLARITY} />);
    await choose(true, true);
    expect(document.getElementById(CLARITY_SCRIPT_ID)).toBeNull();
    expect(document.getElementById(GA_SCRIPT_ID)).not.toBeNull();
  });
});
