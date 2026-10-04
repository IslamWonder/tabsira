import type { Metadata } from 'next';
import { siteOrigin } from '@/lib/site';
import { messages, siteLanguage } from '@/messages';

/*
 * The one place that builds what search engines and share previews read
 * (docs/SEO.md). Every page, today's and the ones still to come (insight,
 * place, public profile), goes through these helpers, so the canonical form,
 * hreflang, share tags and structured data cannot drift from page to page.
 */

/** Routes in the sitemap's static list and indexed. The API's `static` section must carry all of them. */
export const INDEXED_ROUTES = ['/', '/terms', '/privacy', '/support'] as const;

/**
 * Routes served but outside the sitemap: every one answers `noindex`
 * (docs/SEO.md §1). `/admin` and `/dev` live on their own hosts or only under
 * `next dev`, and are disallowed in robots.txt as well.
 */
export const UNLISTED_ROUTES = [
  '/world',
  '/community',
  '/community/publish',
  '/atlas',
  '/atlas/publish',
  '/me',
  '/offline',
  '/signin',
  '/signup',
  '/forgot-password',
  '/reset-password',
  '/verify-email',
] as const;

/** Paths robots.txt keeps every crawler out of (and which are `noindex` as well). */
export const PRIVATE_PATHS = ['/me', '/admin', '/dev', '/api', '/consent'] as const;

/** The default share card (public/share/default.jpg), drawn from the logo by scripts/make-icons.mjs. */
export const SHARE_IMAGE = {
  url: '/share/default.jpg',
  width: 1200,
  height: 630,
  alt: messages.meta.title,
} as const;

export interface ShareImage {
  url: string;
  width: number;
  height: number;
  alt: string;
}

/** `https://tabsira.me/<path>`, with no trailing slash except for the home page, which is the origin itself. */
export function absoluteUrl(path: string): string {
  const url = new URL(path, siteOrigin());
  return url.pathname === '/' ? url.toString() : url.toString().replace(/\/$/, '');
}

export interface PageSeo {
  /** The route, such as `/terms`: used for the canonical, hreflang, og:url and breadcrumbs. */
  path: string;
  /** The page's name; the layout's template adds the site name unless `absoluteTitle` is set. */
  title: string;
  /** At most 165 characters. */
  description: string;
  /** The reason to tap, when it differs from the description. */
  share?: string;
  /** The title stands alone (the home page). */
  absoluteTitle?: boolean;
  /** `article` for insights and posts. */
  type?: 'website' | 'article';
  /** A card of the page's own; the default one otherwise. */
  image?: ShareImage;
  /** A legal text is shown whole, never quoted in part by a result. */
  noSnippet?: boolean;
  /** A withdrawn or private item: kept out of results. */
  noindex?: boolean;
}

function fullTitle({ title, absoluteTitle }: PageSeo): string {
  return absoluteTitle === true ? title : messages.meta.titleTemplate.replace('%s', title);
}

function robotsFor({ noindex, noSnippet }: PageSeo): NonNullable<Metadata['robots']> {
  if (noindex === true) {
    return { index: false, follow: false };
  }
  return noSnippet === true
    ? { index: true, follow: true, 'max-snippet': 0 }
    : { index: true, follow: true };
}

/** Metadata of one indexable page, or of an item that must stay out of results (`noindex`). */
export function pageMetadata(seo: PageSeo): Metadata {
  const { path, title, description, share, absoluteTitle, type = 'website' } = seo;
  const shown = fullTitle(seo);
  const shareText = share ?? description;
  const images = [seo.image ?? SHARE_IMAGE];
  return {
    title: absoluteTitle === true ? { absolute: title } : title,
    description,
    alternates: { canonical: path, languages: { ar: path, 'x-default': path } },
    robots: robotsFor(seo),
    openGraph: {
      type,
      locale: siteLanguage.ogLocale,
      siteName: messages.meta.siteName,
      title: shown,
      description: shareText,
      url: path,
      images,
    },
    twitter: { card: 'summary_large_image', title: shown, description: shareText, images },
  };
}

/** A route outside the sitemap (docs/SEO.md §1): `noindex`, still self-canonical and with a card. */
export function unlistedMetadata(seo: Pick<PageSeo, 'path' | 'title'> & { description?: string }) {
  return pageMetadata({
    ...seo,
    description: seo.description ?? messages.meta.description,
    noindex: true,
  });
}

type JsonLd = Record<string, unknown>;

const ORGANIZATION_ID = () => `${absoluteUrl('/')}#organization`;
const WEBSITE_ID = () => `${absoluteUrl('/')}#website`;

/**
 * The organisation, with a stable `@id` and the square logo. `sameAs` and the
 * founders are left out until the owners give the profile addresses and the
 * site prints the founders: JSON-LD never states what the page does not.
 */
export function organizationJsonLd(sameAs: readonly string[] = []): JsonLd {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    '@id': ORGANIZATION_ID(),
    name: messages.meta.siteName,
    url: absoluteUrl('/'),
    logo: {
      '@type': 'ImageObject',
      url: absoluteUrl('/icons/icon-512.png'),
      width: 512,
      height: 512,
    },
    description: messages.seo.organizationDescription,
    ...(sameAs.length === 0 ? {} : { sameAs }),
  };
}

export function webSiteJsonLd(): JsonLd {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': WEBSITE_ID(),
    name: messages.meta.siteName,
    url: absoluteUrl('/'),
    inLanguage: siteLanguage.tag,
    publisher: { '@id': ORGANIZATION_ID() },
  };
}

/** schema.org WebPage for one page; every field is printed on the page itself. */
export function webPageJsonLd(
  { path, title, description }: Pick<PageSeo, 'path' | 'title' | 'description'>,
  dateModified?: string
): JsonLd {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: title,
    description,
    url: absoluteUrl(path),
    inLanguage: siteLanguage.tag,
    isPartOf: { '@id': WEBSITE_ID() },
    ...(dateModified === undefined ? {} : { dateModified }),
  };
}

export interface Crumb {
  name: string;
  path: string;
}

/** The trail of a non-home page: the home page, then `crumbs` in order. */
export function breadcrumbJsonLd(crumbs: readonly Crumb[]): JsonLd {
  const trail = [{ name: messages.seo.home, path: '/' }, ...crumbs];
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map(({ name, path }, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name,
      item: absoluteUrl(path),
    })),
  };
}

/**
 * For public insights and posts: the headline, the date and the author's
 * public display name only (docs/SEO.md §3). Never scripture, never a
 * location.
 */
export function articleJsonLd(article: {
  path: string;
  headline: string;
  datePublished: string;
  authorName: string;
  dateModified?: string;
}): JsonLd {
  return {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: article.headline,
    url: absoluteUrl(article.path),
    inLanguage: siteLanguage.tag,
    datePublished: article.datePublished,
    ...(article.dateModified === undefined ? {} : { dateModified: article.dateModified }),
    author: { '@type': 'Person', name: article.authorName },
    publisher: { '@id': ORGANIZATION_ID() },
  };
}
