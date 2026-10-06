import { describe, expect, it } from 'vitest';
import { AI_AGENTS } from '@/lib/crawlers';
import { llmsFullTxt, llmsTxt } from '@/lib/llms';
import { messages } from '@/messages';
import { GET as getLlms } from '../app/llms.txt/route';
import { GET as getLlmsFull } from '../app/llms-full.txt/route';
import robots from '../app/robots';
import {
  absoluteUrl,
  articleJsonLd,
  breadcrumbJsonLd,
  INDEXED_ROUTES,
  organizationJsonLd,
  PRIVATE_PATHS,
  pageMetadata,
  SHARE_IMAGE,
  UNLISTED_ROUTES,
  unlistedMetadata,
  webPageJsonLd,
  webSiteJsonLd,
} from './seo';

const PAGE = { path: '/terms', title: 'شروط الاستخدام', description: 'وصف الصفحة' } as const;

describe('addresses', () => {
  it('uses one form: no trailing slash, except the home page which is the origin', () => {
    expect(absoluteUrl('/')).toBe('https://tabsira.test/');
    expect(absoluteUrl('/terms')).toBe('https://tabsira.test/terms');
    expect(absoluteUrl('/terms/')).toBe('https://tabsira.test/terms');
  });

  it('lists no route as both indexed and unlisted', () => {
    expect(
      INDEXED_ROUTES.filter((route) => (UNLISTED_ROUTES as readonly string[]).includes(route))
    ).toEqual([]);
  });
});

describe('page metadata', () => {
  it('is self-canonical with ar and x-default, a share card and Arabic locale', () => {
    const metadata = pageMetadata(PAGE);
    expect(metadata.title).toBe('شروط الاستخدام');
    expect(metadata.alternates).toEqual({
      canonical: '/terms',
      languages: { ar: '/terms', 'x-default': '/terms' },
    });
    expect(metadata.robots).toEqual({ index: true, follow: true });
    expect(metadata.openGraph).toMatchObject({
      type: 'website',
      locale: 'ar_AR',
      url: '/terms',
      title: 'شروط الاستخدام · تبصرة',
      description: 'وصف الصفحة',
      images: [SHARE_IMAGE],
    });
    expect(metadata.twitter).toMatchObject({ card: 'summary_large_image', images: [SHARE_IMAGE] });
  });

  it('takes a share line, an article type, a card of its own and no snippet', () => {
    const image = { url: '/c.jpg', width: 1200, height: 630, alt: 'x' };
    const metadata = pageMetadata({
      ...PAGE,
      share: 'سبب النقر',
      type: 'article',
      image,
      noSnippet: true,
    });
    expect(metadata.robots).toEqual({ index: true, follow: true, 'max-snippet': 0 });
    expect(metadata.openGraph).toMatchObject({
      type: 'article',
      description: 'سبب النقر',
      images: [image],
    });
    expect(metadata.description).toBe('وصف الصفحة');
  });

  it('lets a title stand alone, for the home page', () => {
    const metadata = pageMetadata({ ...PAGE, path: '/', absoluteTitle: true });
    expect(metadata.title).toEqual({ absolute: 'شروط الاستخدام' });
    expect(metadata.openGraph).toMatchObject({ title: 'شروط الاستخدام' });
  });

  it('keeps a withdrawn item out of results', () => {
    expect(pageMetadata({ ...PAGE, noindex: true }).robots).toEqual({
      index: false,
      follow: false,
    });
  });

  it('describes an unlisted route as noindex, with the site description unless it has its own', () => {
    expect(unlistedMetadata({ path: '/me', title: 'ملفي' })).toMatchObject({
      description: messages.meta.description,
      robots: { index: false, follow: false },
    });
    expect(unlistedMetadata({ path: '/me', title: 'ملفي', description: 'خاص' }).description).toBe(
      'خاص'
    );
  });
});

describe('structured data', () => {
  it('describes the organisation with a stable id and a square logo, and no unprinted facts', () => {
    const organization = organizationJsonLd();
    expect(organization).toMatchObject({
      '@type': 'Organization',
      '@id': 'https://tabsira.test/#organization',
      name: 'تبصرة',
      logo: { url: 'https://tabsira.test/icons/icon-512.png', width: 512, height: 512 },
    });
    expect(organization).not.toHaveProperty('sameAs');
    expect(organization).not.toHaveProperty('founder');
    expect(organizationJsonLd(['https://example.org/tabsira'])).toMatchObject({
      sameAs: ['https://example.org/tabsira'],
    });
  });

  it('describes the site, in Arabic, published by the organisation', () => {
    expect(webSiteJsonLd()).toMatchObject({
      '@type': 'WebSite',
      '@id': 'https://tabsira.test/#website',
      inLanguage: 'ar',
      publisher: { '@id': 'https://tabsira.test/#organization' },
    });
  });

  it('describes a page as part of the site, with its date when it has one', () => {
    expect(webPageJsonLd(PAGE, '2026-10-04')).toMatchObject({
      '@type': 'WebPage',
      url: 'https://tabsira.test/terms',
      isPartOf: { '@id': 'https://tabsira.test/#website' },
      dateModified: '2026-10-04',
    });
    expect(webPageJsonLd(PAGE)).not.toHaveProperty('dateModified');
  });

  it('describes the trail from the home page', () => {
    expect(breadcrumbJsonLd([{ name: 'شروط الاستخدام', path: '/terms' }])).toEqual({
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'الرئيسية', item: 'https://tabsira.test/' },
        {
          '@type': 'ListItem',
          position: 2,
          name: 'شروط الاستخدام',
          item: 'https://tabsira.test/terms',
        },
      ],
    });
  });

  it('describes an article by its headline, date and public author name only', () => {
    const article = articleJsonLd({
      path: '/insights/x',
      headline: 'عنوان',
      datePublished: '2026-10-04',
      authorName: 'اسم العرض',
    });
    expect(article).toMatchObject({
      '@type': 'Article',
      headline: 'عنوان',
      datePublished: '2026-10-04',
      author: { '@type': 'Person', name: 'اسم العرض' },
    });
    expect(article).not.toHaveProperty('dateModified');
    expect(
      articleJsonLd({ path: '/insights/x', headline: 'عنوان', datePublished: '2026-10-04' })
    ).not.toHaveProperty('author');
    expect(
      articleJsonLd({
        path: '/insights/x',
        headline: 'عنوان',
        datePublished: '2026-10-04',
        authorName: 'اسم',
        dateModified: '2026-10-05',
      })
    ).toMatchObject({ dateModified: '2026-10-05' });
  });
});

describe('robots.txt', () => {
  it('names every AI agent, closes the private areas, and names the sitemap index only', () => {
    const { rules, sitemap, host } = robots();
    const [rule] = Array.isArray(rules) ? rules : [rules];
    expect(rule?.userAgent).toEqual(['*', ...AI_AGENTS]);
    expect(AI_AGENTS).toHaveLength(17);
    expect(rule?.allow).toBe('/');
    expect(rule?.disallow).toEqual([...PRIVATE_PATHS]);
    for (const path of ['/me', '/sky', '/admin', '/dev', '/api']) {
      expect(rule?.disallow).toContain(path);
    }
    expect(sitemap).toBe('https://tabsira.test/sitemap.xml');
    expect(host).toBeUndefined();
  });
});

describe('llms.txt', () => {
  it('lists the public pages by their absolute address and the rules for readers', async () => {
    const text = llmsTxt();
    expect(text).toContain('# تبصرة');
    expect(text).toContain('https://tabsira.test/terms');
    expect(text).toContain('https://tabsira.test/support');
    expect(text).not.toContain('/me');
    const response = getLlms();
    expect(response.headers.get('Content-Type')).toBe('text/plain; charset=utf-8');
    expect(await response.text()).toBe(text);
  });

  it('carries the legal texts whole in the full version', async () => {
    const text = llmsFullTxt();
    expect(text.startsWith(llmsTxt().trimEnd())).toBe(true);
    expect(text).toContain('### ملفات تعريف الارتباط وخياراتك');
    expect(text).toContain('- ');
    expect(await getLlmsFull().text()).toBe(text);
  });
});
