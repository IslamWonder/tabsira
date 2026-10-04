import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiError, mockApi, type Route } from '@/test/api';
import { USER } from '@/test/fixtures';
import { IDENTITY, MY_POST, POST, page } from '@/test/social';
import { CommunityScreen, tabFromHash } from './community-screen';

vi.mock('next/navigation', () => ({ usePathname: () => '/community' }));

// A tab is remembered in the fragment; each test starts on «لك».
beforeEach(() => window.history.replaceState(null, '', '/community'));

const SECOND = {
  ...POST,
  id: '7345678901234567899',
  insight: { ...POST.insight, title: '[بصيرة ثانية]' },
};

function guest(extra: Record<string, Route> = {}) {
  return mockApi({
    'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
    'GET /feed/for-you': { body: page([{ ...POST, why: { code: 'fresh', text: '[حديثة]' } }]) },
    'GET /feed/latest': { body: page([], null, 'no_posts') },
    ...extra,
  });
}

function member(extra: Record<string, Route> = {}) {
  return mockApi({
    'GET /auth/me': { body: USER },
    'GET /me/public-identity': { body: IDENTITY },
    'GET /feed/for-you': { body: page([POST]) },
    ...extra,
  });
}

describe('CommunityScreen for a guest', () => {
  it('opens on «لك» with the reason of each post, and gates «أتابع» behind sign-in', async () => {
    guest();
    render(<CommunityScreen />);
    expect(screen.getByRole('heading', { level: 1, name: 'تبصرة تواصل' })).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { level: 2, name: '[عنوان البصيرة]' })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /\[حديثة\] لماذا أرى هذا؟/ })).toBeInTheDocument();
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'لك',
      'أتابع',
      'الأحدث',
    ]);

    await userEvent.click(screen.getByRole('tab', { name: 'أتابع' }));
    expect(screen.getByText('ادخل لترى بصائر من تتابعهم.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'ادخل' })).toHaveAttribute(
      'href',
      '/signin?next=%2Fcommunity'
    );
    expect(window.location.hash).toBe('#following');

    await userEvent.click(screen.getByRole('tab', { name: 'الأحدث' }));
    expect(await screen.findByRole('status')).toHaveTextContent('لا منشورات هنا بعد.');
  });

  it('loads the next page on request and says when the list ends', async () => {
    const api = guest({
      'GET /feed/for-you': (request) =>
        new URL(request.url).searchParams.get('cursor') === 'c1'
          ? { body: page([SECOND]) }
          : { body: page([POST], 'c1') },
    });
    render(<CommunityScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'اعرض المزيد' }));
    expect(
      await screen.findByRole('heading', { level: 2, name: '[بصيرة ثانية]' })
    ).toBeInTheDocument();
    expect(screen.getByText('هذا كل ما نُشر حتى الآن.')).toBeInTheDocument();
    expect(api.requests.filter((r) => r.url.includes('/feed/for-you'))).toHaveLength(2);
  });

  it('says when the feed cannot be loaded and tries again', async () => {
    guest({ 'GET /feed/for-you': 'network-error' });
    render(<CommunityScreen />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/تعذّر الوصول إلى تبصرة/);
    guest();
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(
      await screen.findByRole('heading', { level: 2, name: '[عنوان البصيرة]' })
    ).toBeInTheDocument();
  });
});

describe('CommunityScreen for a member', () => {
  it('adds «منشوراتي» and «محفوظاتي», with their own empty states', async () => {
    member({
      'GET /me/posts': { body: { items: [{ ...MY_POST, status: 'draft' }], next_cursor: null } },
      'GET /me/bookmarks': { body: page([], null, 'no_posts') },
      'GET /feed/following': { body: page([], null, 'follows_nobody') },
    });
    render(<CommunityScreen />);
    await waitFor(() => expect(screen.getAllByRole('tab')).toHaveLength(5));
    expect(screen.getByRole('link', { name: 'انشر بصيرة من عالمك' })).toHaveAttribute(
      'href',
      '/community/publish'
    );

    await userEvent.click(screen.getByRole('tab', { name: 'منشوراتي' }));
    const status = await screen.findByTestId('post-status');
    expect(within(status).getByText('مسودة')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'محفوظاتي' }));
    expect(await screen.findByText(/لم تحفظ منشورًا بعد/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'أتابع' }));
    expect(await screen.findByText(/لا تتابع أحدًا بعد/)).toBeInTheDocument();
  });

  it('removes a withdrawn post from the list', async () => {
    member({
      'GET /feed/for-you': { body: page([MY_POST]) },
      'DELETE /posts/7345678901234567890': { status: 204 },
    });
    render(<CommunityScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'المزيد' }));
    await userEvent.click(screen.getByRole('button', { name: 'اسحب المنشور' }));
    await userEvent.click(screen.getByRole('button', { name: 'اسحب' }));
    await waitFor(() =>
      expect(screen.queryByRole('heading', { level: 2, name: '[عنوان البصيرة]' })).toBeNull()
    );
  });
});

describe('tabFromHash', () => {
  it('names a tab from the fragment and falls back to «لك»', () => {
    expect(tabFromHash('#latest')).toBe('latest');
    expect(tabFromHash('#saved')).toBe('saved');
    expect(tabFromHash('')).toBe('for-you');
    expect(tabFromHash('#nothing')).toBe('for-you');
  });
});
