import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { decide, forgetConsent } from '@/consent/store';
import { mockApi } from '@/test/api';
import { POLICY, RECORD } from '@/test/fixtures';
import { CLARITY_SCRIPT_ID, pauseClarity, startClarity, stopClarity } from './clarity';
import { domainsOf, expireCookies } from './cookies';
import { dropQueuedEvents, flushEvents, track } from './events';
import {
  GA_SCRIPT_ID,
  pauseGoogleAnalytics,
  startGoogleAnalytics,
  stopGoogleAnalytics,
} from './google';
import { isExcludedPath } from './paths';

const gtag = vi.fn();
const sent = () => gtag.mock.calls.filter(([command]) => command === 'event');
const flags = () => window as unknown as Record<string, unknown>;
const clarityQueue = () => (window as unknown as { clarity: { q: unknown[][] } }).clarity.q;

function seedCookie(cookie: string) {
  // biome-ignore lint/suspicious/noDocumentCookie: seeding jsdom's cookie jar for the test.
  document.cookie = `${cookie}; Path=/`;
}

beforeEach(() => {
  gtag.mockClear();
  vi.stubGlobal('gtag', gtag);
  window.history.replaceState(null, '', '/');
});

afterEach(() => {
  dropQueuedEvents();
  document.getElementById(GA_SCRIPT_ID)?.remove();
  document.getElementById(CLARITY_SCRIPT_ID)?.remove();
  Reflect.deleteProperty(window, 'clarity');
  Reflect.deleteProperty(window, 'ga-disable-G-TEST1234');
  forgetConsent();
});

async function accept(analytics: boolean, behaviour = false) {
  mockApi({
    'GET /consent/policy': { body: POLICY },
    'POST /consent': { body: { ...RECORD, categories: { necessary: true, analytics, behaviour } } },
  });
  await decide({ necessary: true, analytics, behaviour });
}

describe('the pages where no tool runs', () => {
  it('are the admin, developer, sign-in and account areas, by path only', () => {
    for (const path of [
      '/admin',
      '/admin/users',
      '/dev/ui',
      '/signin',
      '/signup',
      '/me',
      '/reset-password',
      '/verify-email',
      '/forgot-password',
      '/login',
    ]) {
      expect(isExcludedPath(path), path).toBe(true);
    }
    for (const path of ['/', '/world', '/terms', '/mex', '/device', '/signing']) {
      expect(isExcludedPath(path), path).toBe(false);
    }
  });
});

describe('deleting the cookies of a tool', () => {
  it('tries the host and every parent domain, and not an address', () => {
    expect(domainsOf('a.tabsira.me')).toEqual([null, '.a.tabsira.me', '.tabsira.me']);
    expect(domainsOf('127.0.0.1')).toEqual([null]);
    expect(domainsOf('localhost')).toEqual([null]);
  });

  it('removes the matching cookies and keeps the others', () => {
    seedCookie('_ga=1');
    seedCookie('_ga_AB12=2');
    seedCookie('keep=3');
    expireCookies(/^_ga(_.*)?$/);
    expect(document.cookie).toBe('keep=3');
  });
});

describe('product events', () => {
  it('send nothing until the analytics category is accepted, and nothing when it is refused', async () => {
    track('share', { method: 'link', kind: 'insight' });
    await accept(false, true);
    track('share', { method: 'link', kind: 'insight' });
    expect(sent()).toEqual([]);
  });

  it('send nothing when no Google code is configured', async () => {
    vi.stubGlobal('gtag', undefined);
    await accept(true);
    expect(() => track('done_pressed', { context: 'insight' })).not.toThrow();
  });

  it('are sent with fixed words, numbers and booleans only', async () => {
    await accept(true);
    track('scan_finished', { outcome: 'insight', seconds: 12 });
    track('consent_changed', { analytics: true, behaviour: false });
    // A value that is not a fixed word never leaves, whatever the types say.
    track('share', { method: 'a note about Sarah', kind: 'insight' } as never);
    track('scan_finished', { outcome: 'failed', seconds: Number.NaN });
    expect(sent()).toEqual([
      ['event', 'scan_finished', { outcome: 'insight', seconds: 12 }],
      ['event', 'consent_changed', { analytics: true, behaviour: false }],
      ['event', 'share', { kind: 'insight' }],
      ['event', 'scan_finished', { outcome: 'failed' }],
    ]);
  });

  it('wait in memory on a page where no tool runs, and go out on the next page that allows one', async () => {
    await accept(true);
    window.history.replaceState(null, '', '/signup');
    track('sign_up_completed', { method: 'email' });
    flushEvents();
    expect(sent()).toEqual([]);
    window.history.replaceState(null, '', '/world');
    flushEvents();
    expect(sent()).toEqual([['event', 'sign_up_completed', { method: 'email' }]]);
    flushEvents();
    expect(sent()).toHaveLength(1);
  });

  it('keep the last ten, and are dropped on withdrawal', async () => {
    await accept(true);
    window.history.replaceState(null, '', '/me');
    for (let count = 0; count < 12; count += 1) {
      track('scan_finished', { outcome: 'none', seconds: count });
    }
    window.history.replaceState(null, '', '/');
    flushEvents();
    expect(sent()).toHaveLength(10);
    window.history.replaceState(null, '', '/me');
    track('done_pressed', { context: 'insight' });
    dropQueuedEvents();
    window.history.replaceState(null, '', '/');
    flushEvents();
    expect(sent()).toHaveLength(10);
  });

  it('are not flushed after a withdrawal', async () => {
    await accept(true);
    window.history.replaceState(null, '', '/me');
    track('done_pressed', { context: 'insight' });
    await accept(false);
    window.history.replaceState(null, '', '/');
    flushEvents();
    expect(sent()).toEqual([]);
  });
});

describe('Google Analytics 4', () => {
  it('loads nothing when the Consent Mode defaults did not run', () => {
    vi.stubGlobal('gtag', undefined);
    startGoogleAnalytics('G-TEST1234');
    expect(document.getElementById(GA_SCRIPT_ID)).toBeNull();
  });

  it('is configured once, with the path of the page and no query, and a referrer reduced to its origin', () => {
    window.history.replaceState(null, '', '/world?q=secret#part');
    vi.spyOn(document, 'referrer', 'get').mockReturnValue('https://example.org/a?email=x');
    startGoogleAnalytics('G-TEST1234');
    startGoogleAnalytics('G-TEST1234');
    const script = document.getElementById(GA_SCRIPT_ID) as HTMLScriptElement;
    expect(script.src).toBe('https://www.googletagmanager.com/gtag/js?id=G-TEST1234');
    expect(document.querySelectorAll(`#${GA_SCRIPT_ID}`)).toHaveLength(1);
    const config = gtag.mock.calls.filter(([command]) => command === 'config');
    expect(config).toEqual([
      [
        'config',
        'G-TEST1234',
        {
          allow_google_signals: false,
          allow_ad_personalization_signals: false,
          page_location: `${window.location.origin}/world`,
          page_referrer: 'https://example.org/',
        },
      ],
    ]);
    expect(gtag).toHaveBeenCalledWith('consent', 'update', { analytics_storage: 'granted' });
  });

  it('passes no referrer when there is none', () => {
    startGoogleAnalytics('G-TEST1234');
    expect(gtag.mock.calls.find(([command]) => command === 'config')?.[2]).toMatchObject({
      page_referrer: undefined,
    });
  });

  it('is paused on a page where no tool runs, and resumed on the next', () => {
    pauseGoogleAnalytics('G-TEST1234');
    expect(flags()['ga-disable-G-TEST1234']).toBe(true);
    startGoogleAnalytics('G-TEST1234');
    expect(flags()['ga-disable-G-TEST1234']).toBe(false);
  });

  it('stops on withdrawal: storage denied, the switch on, the _ga cookies gone', () => {
    seedCookie('_ga=GA1.1.1');
    seedCookie('_ga_TEST1234=GS2');
    stopGoogleAnalytics('G-TEST1234');
    expect(gtag).toHaveBeenCalledWith('consent', 'update', { analytics_storage: 'denied' });
    expect(flags()['ga-disable-G-TEST1234']).toBe(true);
    expect(document.cookie).toBe('');
    vi.stubGlobal('gtag', undefined);
    expect(() => stopGoogleAnalytics('G-TEST1234')).not.toThrow();
  });
});

describe('Microsoft Clarity', () => {
  it('is injected once, with advertising storage denied, then restarted rather than loaded again', () => {
    startClarity('abc123xyz9');
    const script = document.getElementById(CLARITY_SCRIPT_ID) as HTMLScriptElement;
    expect(script.src).toBe('https://www.clarity.ms/tag/abc123xyz9');
    const queued = clarityQueue();
    expect(queued).toEqual([['consentv2', { ad_Storage: 'denied', analytics_Storage: 'granted' }]]);
    pauseClarity();
    startClarity('abc123xyz9');
    expect(document.querySelectorAll(`#${CLARITY_SCRIPT_ID}`)).toHaveLength(1);
    expect(clarityQueue().map(([command]) => command)).toEqual([
      'consentv2',
      'stop',
      'consentv2',
      'start',
    ]);
  });

  it('does nothing when paused before it was ever loaded', () => {
    pauseClarity();
    expect((window as unknown as { clarity?: unknown }).clarity).toBeUndefined();
  });

  it('stops on withdrawal: storage denied, recording stopped, its cookies gone', () => {
    seedCookie('_clck=1');
    seedCookie('_clsk=2');
    stopClarity();
    expect(document.cookie).toBe('');
    startClarity('abc123xyz9');
    stopClarity();
    expect(clarityQueue().slice(-2)).toEqual([
      ['consentv2', { ad_Storage: 'denied', analytics_Storage: 'denied' }],
      ['stop'],
    ]);
  });
});
