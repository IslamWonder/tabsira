import { describe, expect, it } from 'vitest';
import { LEGAL_PATHS, legalMetadata, webPageJsonLd } from './legal-seo';

const SEO = { path: '/terms', title: 'شروط الاستخدام', description: 'وصف' } as const;

describe('legal SEO', () => {
  it('lists the three public paths', () => {
    expect(LEGAL_PATHS).toEqual(['/terms', '/privacy', '/support']);
  });

  it('indexes the page with its own canonical, ar and x-default, and no snippet', () => {
    const metadata = legalMetadata(SEO);
    expect(metadata.alternates).toEqual({
      canonical: '/terms',
      languages: { ar: '/terms', 'x-default': '/terms' },
    });
    expect(metadata.robots).toEqual({ index: true, follow: true, 'max-snippet': 0 });
    expect(metadata.openGraph).toMatchObject({ type: 'website', locale: 'ar_AR', url: '/terms' });
    expect(metadata.twitter).toMatchObject({ card: 'summary_large_image' });
  });

  it('describes a WebPage with the absolute address and the date when it has one', () => {
    expect(webPageJsonLd(SEO, '2026-10-04')).toEqual({
      '@context': 'https://schema.org',
      '@type': 'WebPage',
      name: 'شروط الاستخدام',
      description: 'وصف',
      url: 'https://tabsira.test/terms',
      inLanguage: 'ar',
      isPartOf: { '@id': 'https://tabsira.test/#website' },
      dateModified: '2026-10-04',
    });
    expect(webPageJsonLd(SEO)).not.toHaveProperty('dateModified');
  });
});
