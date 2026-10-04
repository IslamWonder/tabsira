import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { PREFERENCES_INIT_SCRIPT } from '@/preferences/init-script';
import RootLayout, { metadata, viewport } from './layout';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

function renderLayout() {
  return new DOMParser().parseFromString(
    renderToStaticMarkup(
      <RootLayout>
        <p>[محتوى]</p>
      </RootLayout>
    ),
    'text/html'
  );
}

describe('RootLayout', () => {
  it('is an Arabic, right-to-left document carrying every font variable', () => {
    const html = renderLayout().documentElement;
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

  it('applies a stored theme and motion choice in <head>, before anything paints', () => {
    const document = renderLayout();
    const script = document.head.querySelector('script');
    expect(script?.textContent).toBe(PREFERENCES_INIT_SCRIPT);
  });

  it('opens with the skip link, then the top bar, the main content, the phone bar and the burst layer', () => {
    const body = renderLayout().body;
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
    expect(body.querySelectorAll('canvas')).toHaveLength(2);
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
