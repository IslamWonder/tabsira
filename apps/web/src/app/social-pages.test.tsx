import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { POST, PROFILE } from '@/test/social';
import PostPage, { generateMetadata as postMetadata } from './posts/[id]/page';
import ProfilePage, { generateMetadata as profileMetadata } from './u/[handle]/page';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

/*
 * The public pages of the social network tell search engines only what a
 * stranger may read, and nothing when the API does not answer (docs/SEO.md).
 * Both pages ask the API from the server: no cookie ever travels with it.
 */

const params = <T extends Record<string, string>>(value: T) => ({ params: Promise.resolve(value) });
const NOINDEX = { index: false, follow: false };

describe('the post page metadata', () => {
  it('describes a public post by its title, glimpse and author, as an article', async () => {
    const api = mockApi({ [`GET /posts/${POST.id}`]: { body: POST } });
    const metadata = await postMetadata(params({ id: POST.id }));
    expect(metadata.title).toBe('[عنوان البصيرة]');
    expect(metadata.description).toBe('[لمحة البصيرة]');
    expect(metadata.alternates?.canonical).toBe(`/posts/${POST.id}`);
    expect(metadata.robots).toMatchObject({ index: true });
    expect(metadata.openGraph).toMatchObject({ type: 'article' });
    // Nothing of the viewer is sent: the server reads the post as a stranger would.
    expect(api.requests[0]?.headers.get('cookie')).toBeNull();
    expect(JSON.stringify(metadata)).not.toContain('example.com');
  });

  it.each([
    ['a post nobody may see', apiError(404, 'NOT_FOUND')],
    ['a withdrawn post', apiError(410, 'GONE')],
    ['an API that does not answer', 'network-error' as const],
  ])('keeps %s out of search results, with the generic title', async (_case, route) => {
    mockApi({ [`GET /posts/${POST.id}`]: route });
    const metadata = await postMetadata(params({ id: POST.id }));
    expect(metadata.robots).toEqual(NOINDEX);
    expect(metadata.title).toBe('تبصرة تواصل');
    expect(metadata.description).not.toContain('[');
  });

  it('never asks the API about an id that is not a public id', async () => {
    const api = mockApi({});
    const metadata = await postMetadata(params({ id: '../../admin' }));
    expect(metadata.robots).toEqual(NOINDEX);
    expect(api.requests).toHaveLength(0);
  });

  it('renders the article data for a published post and the screen for any id', async () => {
    mockApi({ [`GET /posts/${POST.id}`]: { body: POST } });
    const { container } = render(await PostPage(params({ id: POST.id })));
    const jsonLd = container.querySelector('script[type="application/ld+json"]');
    expect(jsonLd?.textContent).toContain('"@type":"Article"');
    expect(jsonLd?.textContent).toContain('"name":"[اسم عام]"');
    expect(jsonLd?.textContent).not.toContain('rain_reader');
    expect(screen.getByText('نحمّل المنشورات…')).toBeInTheDocument();

    mockApi({});
    const bare = render(await PostPage(params({ id: 'nope' })));
    expect(bare.container.querySelector('script[type="application/ld+json"]')).toBeNull();
  });
});

describe('the post page for an author who shows no full name', () => {
  it('renders the article data without an author name, the handle never standing for it', async () => {
    mockApi({
      [`GET /posts/${POST.id}`]: {
        body: { ...POST, author: { handle: 'rain_reader', public_name: null } },
      },
    });
    const { container } = render(await PostPage(params({ id: POST.id })));
    const jsonLd = container.querySelector('script[type="application/ld+json"]');
    expect(jsonLd?.textContent).toContain('"@type":"Article"');
    expect(jsonLd?.textContent).not.toContain('rain_reader');
  });
});

describe('the profile page metadata', () => {
  it('names the member by public name and handle only, once they have a public post', async () => {
    const api = mockApi({ 'GET /u/rain_reader': { body: PROFILE } });
    const metadata = await profileMetadata(params({ handle: 'rain_reader' }));
    expect(metadata.title).toBe('[اسم عام]');
    expect(metadata.description).toBe('بصائر [اسم عام] المنشورة في تبصرة تواصل.');
    expect(metadata.alternates?.canonical).toBe('/u/rain_reader');
    expect(metadata.robots).toMatchObject({ index: true });
    expect(api.requests[0]?.headers.get('cookie')).toBeNull();
    expect(JSON.stringify(metadata)).not.toMatch(/2026-10|followers|example/);
  });

  it('keeps a profile without a public post, a missing one and a bad handle out of results', async () => {
    mockApi({ 'GET /u/rain_reader': { body: { ...PROFILE, posts_count: 0 } } });
    expect((await profileMetadata(params({ handle: 'rain_reader' }))).robots).toEqual(NOINDEX);

    mockApi({ 'GET /u/nobody': apiError(404, 'NOT_FOUND') });
    const missing = await profileMetadata(params({ handle: 'nobody' }));
    expect(missing.robots).toEqual(NOINDEX);
    expect(missing.title).toBe('تبصرة تواصل');

    const api = mockApi({});
    const bad = await profileMetadata(params({ handle: '%2E%2E' }));
    expect(bad.robots).toEqual(NOINDEX);
    expect(api.requests).toHaveLength(0);
    // A handle that is not valid percent-encoding is used as it is, and refused by shape.
    expect((await profileMetadata(params({ handle: '%E0%A4%A' }))).robots).toEqual(NOINDEX);
  });

  it('renders the profile screen for the decoded handle', async () => {
    mockApi({});
    render(await ProfilePage(params({ handle: encodeURIComponent('قارئ') })));
    expect(screen.getByText('نحمّل الصفحة…')).toBeInTheDocument();
  });
});
