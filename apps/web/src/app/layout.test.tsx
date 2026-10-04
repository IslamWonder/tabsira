import { existsSync } from 'node:fs';
import path from 'node:path';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CONSENT_MODE_DEFAULTS } from '@/consent/consent-mode';
import { PREFERENCES_INIT_SCRIPT } from '@/preferences/init-script';
import { mockApi } from '@/test/api';
import { POLICY, RECORD } from '@/test/fixtures';
import RootLayout, { metadata, viewport } from './layout';

const PUBLIC = path.resolve(__dirname, '../../public');

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));
const connection = vi.hoisted(() => vi.fn(async () => undefined));
vi.mock('next/server', () => ({ connection }));
const jar = vi.hoisted(() => ({ values: new Map<string, string>() }));
vi.mock('next/headers', () => ({
  cookies: async () => ({
    get: (name: string) => (jar.values.has(name) ? { value: jar.values.get(name) } : undefined),
  }),
}));

// A returning visitor whose choice holds, unless a test says otherwise.
beforeEach(() => {
  jar.values.clear();
  jar.values.set('tabsira_consent', RECORD.consent_id);
  mockApi({
    [`GET /consent/${RECORD.consent_id}`]: { body: RECORD },
    'GET /consent/policy': { body: POLICY },
  });
});

async function renderLayout() {
  return new DOMParser().parseFromString(
    renderToStaticMarkup(
      await RootLayout({
        children: <p>[محتوى]</p>,
      })
    ),
    'text/html'
  );
}

describe('RootLayout', () => {
  it('is an Arabic, right-to-left document carrying every font variable', async () => {
    const html = (await renderLayout()).documentElement;
    expect(html.getAttribute('lang')).toBe('ar');
    expect(html.getAttribute('dir')).toBe('rtl');
    for (const variable of [
      '--font-readex-arabic',
      '--font-readex-latin',
      '--font-reem-kufi',
      '--font-noto-naskh',
      '--font-amiri',
      '--font-uthmanic-hafs',
    ]) {
      expect(html.className).toContain(variable);
    }
  });

  it('applies a stored theme and motion choice in <head>, before anything paints', async () => {
    const document = await renderLayout();
    const scripts = document.head.querySelectorAll('script');
    expect(scripts).toHaveLength(1);
    expect(scripts[0]?.textContent).toBe(PREFERENCES_INIT_SCRIPT);
  });

  it('puts the Consent Mode defaults first in <head> only when GA_MEASUREMENT_ID is set, read per request', async () => {
    vi.stubEnv('GA_MEASUREMENT_ID', 'G-TEST1234');
    const document = await renderLayout();
    const [first, second] = Array.from(document.head.querySelectorAll('script'));
    expect(first?.id).toBe('consent-mode-defaults');
    expect(first?.textContent).toBe(CONSENT_MODE_DEFAULTS);
    expect(second?.textContent).toBe(PREFERENCES_INIT_SCRIPT);
    expect(connection).toHaveBeenCalled();
    // Nothing from Google is loaded: the defaults only.
    expect(document.documentElement.outerHTML).not.toContain('googletagmanager');
  });

  it('opens with the skip link, then the top bar, the main content, the footer, the phone bar and the burst layer', async () => {
    const body = (await renderLayout()).body;
    const skip = body.querySelector('a');
    expect(skip?.getAttribute('href')).toBe('#main');
    const header = body.querySelector('header');
    const main = body.querySelector('main#main');
    expect(main?.textContent).toBe('[محتوى]');
    expect(main?.getAttribute('tabindex')).toBe('-1');
    const navs = body.querySelectorAll('nav[aria-label="التنقل الرئيسي"]');
    expect(navs).toHaveLength(2);
    expect(header?.compareDocumentPosition(main as Node)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(main?.compareDocumentPosition(navs[1] as Node)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    const footer = body.querySelector('footer');
    expect(footer?.textContent).toContain('إعدادات ملفات تعريف الارتباط');
    expect(footer?.querySelector('a[href="/terms"]')?.textContent).toBe('شروط الاستخدام');
    expect(main?.compareDocumentPosition(footer as Node)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(body.querySelectorAll('canvas')).toHaveLength(2);
  });
});

describe('the cookie choice in the first paint', () => {
  it('is in the server HTML already open on a first visit, over an inert page', async () => {
    jar.values.clear();
    const body = (await renderLayout()).body;
    const dialog = body.querySelector('[role="dialog"]');
    expect(dialog?.getAttribute('aria-modal')).toBe('true');
    expect(dialog?.textContent).toContain('اختر ما تسمح به');
    expect(dialog?.querySelector('form')?.getAttribute('action')).toBe('/consent');
    const shell = body.querySelector('main')?.parentElement;
    expect(shell?.hasAttribute('inert')).toBe(true);
    expect(shell?.getAttribute('aria-hidden')).toBe('true');
    // The page stays in sight under a wash, not behind an opaque wall.
    expect(body.querySelector('.fx-scrim')).not.toBeNull();
  });

  it('is absent for a visitor whose choice holds, and the page is the ordinary page', async () => {
    const body = (await renderLayout()).body;
    expect(body.querySelector('[role="dialog"]')).toBeNull();
    const shell = body.querySelector('main')?.parentElement;
    expect(shell?.hasAttribute('inert')).toBe(false);
    expect(shell?.hasAttribute('aria-hidden')).toBe(false);
  });
});

describe('metadata', () => {
  it('names the site, with a title template and short enough text for search results', () => {
    expect(String(metadata.metadataBase)).toBe('https://tabsira.test/');
    expect(metadata.title).toEqual({
      default: 'تبصرة · انظر إلى العالم بعين الوحي',
      template: '%s · تبصرة',
    });
    expect(metadata.applicationName).toBe('تبصرة');
    expect(String(metadata.description).length).toBeLessThanOrEqual(165);
  });

  it('points at the icons and the share card drawn from the logo, every file present', () => {
    const files = [
      '/favicon.ico',
      '/icon.svg',
      '/icons/icon-192.png',
      '/icons/apple-icon.png',
      '/browserconfig.xml',
      '/share/default.jpg',
    ];
    expect(metadata.icons).toEqual({
      icon: [
        { url: '/favicon.ico', sizes: '16x16 32x32 48x48' },
        { url: '/icon.svg', type: 'image/svg+xml', sizes: 'any' },
        { url: '/icons/icon-192.png', type: 'image/png', sizes: '192x192' },
      ],
      apple: { url: '/icons/apple-icon.png', sizes: '180x180' },
    });
    expect(metadata.other).toEqual({
      'msapplication-config': '/browserconfig.xml',
      'msapplication-TileColor': '#0B1210',
    });
    const card = {
      url: '/share/default.jpg',
      width: 1200,
      height: 630,
      alt: 'تبصرة · انظر إلى العالم بعين الوحي',
    };
    expect(metadata.openGraph?.images).toEqual([card]);
    expect(metadata.twitter).toMatchObject({ card: 'summary_large_image', images: [card] });
    for (const file of files) {
      expect(existsSync(path.join(PUBLIC, file)), file).toBe(true);
    }
  });

  it('lets people zoom and follows the safe areas and the device theme', () => {
    expect(viewport).toMatchObject({
      width: 'device-width',
      initialScale: 1,
      viewportFit: 'cover',
    });
    expect(viewport).not.toHaveProperty('maximumScale');
    expect(viewport.themeColor).toEqual([
      { media: '(prefers-color-scheme: light)', color: '#F6FAF7' },
      { media: '(prefers-color-scheme: dark)', color: '#0B1210' },
    ]);
  });
});
