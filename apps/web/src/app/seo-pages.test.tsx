import { describe, expect, it, vi } from 'vitest';
import { INDEXED_ROUTES, UNLISTED_ROUTES } from '@/lib/seo';
import { messages } from '@/messages';
import { metadata as atlas } from './atlas/page';
import { metadata as atlasPublish } from './atlas/publish/page';
import { metadata as community } from './community/page';
import { metadata as publish } from './community/publish/page';
import { metadata as forgot } from './forgot-password/page';
import { metadata as me } from './me/page';
import { metadata as offline } from './offline/page';
import { metadata as home } from './page';
import { metadata as privacy } from './privacy/page';
import { metadata as reset } from './reset-password/page';
import { metadata as signin } from './signin/page';
import { metadata as signup } from './signup/page';
import { metadata as support } from './support/page';
import { metadata as terms } from './terms/page';
import { metadata as verify } from './verify-email/page';
import { metadata as world } from './world/page';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

const INDEXED = { '/': home, '/terms': terms, '/privacy': privacy, '/support': support };
const UNLISTED = {
  '/world': world,
  '/community': community,
  '/community/publish': publish,
  '/atlas': atlas,
  '/atlas/publish': atlasPublish,
  '/me': me,
  '/offline': offline,
  '/signin': signin,
  '/signup': signup,
  '/forgot-password': forgot,
  '/reset-password': reset,
  '/verify-email': verify,
};

function titleOf(title: unknown): string {
  return typeof title === 'string'
    ? messages.meta.titleTemplate.replace('%s', title)
    : (title as { absolute: string }).absolute;
}

describe('metadata on every page (docs/SEO.md §2)', () => {
  it('covers exactly the routes the SEO lists name', () => {
    expect(Object.keys(INDEXED).sort()).toEqual([...INDEXED_ROUTES].sort());
    expect(Object.keys(UNLISTED).sort()).toEqual([...UNLISTED_ROUTES].sort());
  });

  it.each(Object.entries(INDEXED))(
    '%s is indexed, self-canonical, with ar and x-default',
    (path, metadata) => {
      expect(metadata.alternates).toEqual({
        canonical: path,
        languages: { ar: path, 'x-default': path },
      });
      expect(metadata.robots).toMatchObject({ index: true });
    }
  );

  it.each(Object.entries(UNLISTED))(
    '%s is noindex and names its own canonical',
    (path, metadata) => {
      expect(metadata.robots).toEqual({ index: false, follow: false });
      expect(metadata.alternates?.canonical).toBe(path);
    }
  );

  it.each([...Object.entries(INDEXED), ...Object.entries(UNLISTED)])(
    '%s has a title up to 65 characters, a description up to 165, and a share card',
    (_path, metadata) => {
      expect(titleOf(metadata.title).length).toBeLessThanOrEqual(65);
      expect(String(metadata.description).length).toBeGreaterThan(0);
      expect(String(metadata.description).length).toBeLessThanOrEqual(165);
      expect(metadata.openGraph).toMatchObject({ locale: 'ar_AR' });
      expect(metadata.openGraph?.images).toHaveLength(1);
      expect(metadata.twitter).toMatchObject({ card: 'summary_large_image' });
    }
  );

  it('gives the home page its own title and a share line distinct from its description', () => {
    expect(home.title).toEqual({ absolute: messages.meta.title });
    expect(home.openGraph?.description).toBe(messages.seo.homeShare);
    expect(home.openGraph?.description).not.toBe(home.description);
  });
});
