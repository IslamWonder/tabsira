import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { apiError, mockApi, type Route } from '@/test/api';
import { USER } from '@/test/fixtures';
import { IDENTITY, POST, PROFILE, page } from '@/test/social';
import { formatMonth, ProfileScreen } from './profile-screen';

vi.mock('next/navigation', () => ({ usePathname: () => '/u/rain_reader' }));

function member(extra: Record<string, Route> = {}) {
  return mockApi({
    'GET /auth/me': { body: USER },
    'GET /me/public-identity': { body: IDENTITY },
    'GET /u/rain_reader': { body: { ...PROFILE, viewer: { follows: false, is_self: false } } },
    'GET /u/rain_reader/posts': { body: page([POST]) },
    ...extra,
  });
}

describe('ProfileScreen', () => {
  it('says the country after the month joined when the member chose to show it', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /u/rain_reader': { body: { ...PROFILE, country: { code: 'TN', name: 'تونس' } } },
      'GET /u/rain_reader/posts': { body: page([]) },
    });
    render(<ProfileScreen handle="rain_reader" />);
    expect(await screen.findByText(`انضم في ${formatMonth('2026-10')} · تونس`)).toBeInTheDocument();
  });

  it('shows the public name, the handle, the month joined, three counts and the posts', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /u/rain_reader': { body: PROFILE },
      'GET /u/rain_reader/posts': { body: page([POST]) },
    });
    render(<ProfileScreen handle="rain_reader" />);
    expect(await screen.findByRole('heading', { level: 1, name: '[اسم عام]' })).toBeInTheDocument();
    const header = screen.getByRole('region', { name: '[اسم عام]' });
    expect(within(header).getByText('@rain_reader')).toBeInTheDocument();
    expect(screen.getByText(`انضم في ${formatMonth('2026-10')}`)).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { level: 3, name: '[عنوان البصيرة]' })
    ).toBeInTheDocument();
    // A guest is sent to sign in before following.
    expect(screen.getByRole('link', { name: 'ادخل لتتابع' })).toHaveAttribute(
      'href',
      '/signin?next=%2Fu%2Frain_reader'
    );
    // Nothing but the handle and the public name is on the page.
    expect(document.body.textContent).not.toContain('example.com');
  });

  it('heads a profile without a public name with the handle, shown once', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /u/rain_reader': { body: { ...PROFILE, public_name: null } },
      'GET /u/rain_reader/posts': { body: page([POST]) },
    });
    render(<ProfileScreen handle="rain_reader" />);
    const heading = await screen.findByRole('heading', { level: 1 });
    expect(heading).toHaveTextContent('@rain_reader');
    expect(
      within(screen.getByRole('region', { name: '@rain_reader' })).getAllByText('@rain_reader')
    ).toHaveLength(1);
  });

  it('follows and unfollows through the API', async () => {
    const api = member({
      'PUT /u/rain_reader/follow': { status: 204 },
      'DELETE /u/rain_reader/follow': { status: 204 },
    });
    render(<ProfileScreen handle="rain_reader" />);
    const follow = await screen.findByRole('button', { name: 'تابع' });
    await waitFor(() => expect(follow).toBeEnabled());
    await userEvent.click(follow);
    expect(await screen.findByRole('button', { name: 'تتابعه' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByText('6')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'تتابعه' }));
    expect(await screen.findByRole('button', { name: 'تابع' })).toBeInTheDocument();
    expect(api.requests.filter((r) => r.url.endsWith('/follow')).map((r) => r.method)).toEqual([
      'PUT',
      'DELETE',
    ]);
  });

  it('blocks the member from the «more» sheet and then shows nothing of them', async () => {
    member({ 'PUT /blocks/rain_reader': { status: 204 } });
    render(<ProfileScreen handle="rain_reader" />);
    const header = await screen.findByRole('region', { name: '[اسم عام]' });
    await userEvent.click(within(header).getByRole('button', { name: 'المزيد' }));
    await userEvent.click(screen.getByRole('button', { name: 'احجب [اسم عام]' }));
    await userEvent.click(screen.getByRole('button', { name: 'احجب' }));
    expect(await screen.findByText(/حجبت هذا العضو/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole('heading', { level: 1, name: '[اسم عام]' })).toBeNull()
    );
  });

  it('offers its owner the way to edit the identity instead of a follow button', async () => {
    member({
      'GET /u/rain_reader': { body: { ...PROFILE, viewer: { follows: false, is_self: true } } },
    });
    render(<ProfileScreen handle="rain_reader" />);
    expect(await screen.findByRole('link', { name: 'عدّل هويتك العامة' })).toHaveAttribute(
      'href',
      '/me#identity'
    );
    expect(screen.queryByRole('button', { name: 'تابع' })).toBeNull();
    expect(screen.getByText('هذه صفحتك العامة.')).toBeInTheDocument();
  });

  it('says when nobody holds the handle, and when the page cannot be loaded', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /u/nobody': apiError(404, 'NOT_FOUND'),
      'GET /u/nobody/posts': apiError(404, 'NOT_FOUND'),
    });
    render(<ProfileScreen handle="nobody" />);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'لم نجد هذا العضو' })
    ).toBeInTheDocument();

    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /u/rain_reader': 'network-error',
      'GET /u/rain_reader/posts': 'network-error',
    });
    render(<ProfileScreen handle="rain_reader" />);
    expect((await screen.findAllByRole('alert'))[0]).toHaveTextContent(/تعذّر الوصول/);
  });

  it('asks an unverified account to verify before following, unless it already follows', async () => {
    member({ 'GET /auth/me': { body: { ...USER, email_verified: false } } });
    render(<ProfileScreen handle="rain_reader" />);
    expect(await screen.findByText(messages.community.profile.verify)).toBeInTheDocument();
  });

  it('lets an unverified account who already follows unfollow', async () => {
    member({
      'GET /auth/me': { body: { ...USER, email_verified: false } },
      'GET /u/rain_reader': { body: { ...PROFILE, viewer: { follows: true, is_self: false } } },
    });
    render(<ProfileScreen handle="rain_reader" />);
    expect(await screen.findByRole('button', { name: 'تتابعه' })).toBeInTheDocument();
  });

  it('says when following fails and keeps the button as it was', async () => {
    member({ 'PUT /u/rain_reader/follow': apiError(500, 'INTERNAL') });
    render(<ProfileScreen handle="rain_reader" />);
    const follow = await screen.findByRole('button', { name: 'تابع' });
    await waitFor(() => expect(follow).toBeEnabled());
    await userEvent.click(follow);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'تابع' })).toBeInTheDocument();
  });

  it('asks again when the retry is pressed', async () => {
    let calls = 0;
    member({
      'GET /u/rain_reader': () => {
        calls += 1;
        return calls === 1
          ? apiError(500, 'INTERNAL')
          : { body: { ...PROFILE, viewer: { follows: false, is_self: false } } };
      },
    });
    render(<ProfileScreen handle="rain_reader" />);
    await userEvent.click(await screen.findByRole('button', { name: 'أعد المحاولة' }));
    expect(await screen.findByRole('heading', { level: 1, name: '[اسم عام]' })).toBeInTheDocument();
  });

  it('says when the member published nothing', async () => {
    member({ 'GET /u/rain_reader/posts': { body: page([], null, 'no_posts') } });
    render(<ProfileScreen handle="rain_reader" />);
    expect(await screen.findByText(messages.community.profile.noPosts)).toBeInTheDocument();
  });

  it('closes the «more» and block sheets without blocking', async () => {
    member();
    render(<ProfileScreen handle="rain_reader" />);
    const header = await screen.findByRole('region', { name: '[اسم عام]' });
    await userEvent.click(within(header).getByRole('button', { name: 'المزيد' }));
    await userEvent.keyboard('{Escape}');
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'احجب [اسم عام]' })).toBeNull()
    );
    await userEvent.click(within(header).getByRole('button', { name: 'المزيد' }));
    await userEvent.click(screen.getByRole('button', { name: 'احجب [اسم عام]' }));
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByRole('heading', { level: 1, name: '[اسم عام]' })).toBeInTheDocument();
  });

  async function blockFromCard(posts: (typeof POST)[]) {
    member({
      'GET /u/rain_reader/posts': { body: page(posts) },
      'PUT /blocks/other_one': { status: 204 },
    });
    render(<ProfileScreen handle="rain_reader" />);
    await screen.findByRole('heading', { level: 3, name: '[عنوان البصيرة]' });
    await userEvent.click(screen.getAllByRole('button', { name: 'المزيد' }).at(-1) as HTMLElement);
    await userEvent.click(screen.getByRole('button', { name: /^احجب/ }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'احجب' }));
  }

  it('keeps the profile when the author blocked from a card is somebody else', async () => {
    const byOther = { ...POST, author: { handle: 'other_one', public_name: '[عضو آخر]' } };
    await blockFromCard([byOther]);
    await waitFor(() =>
      expect(screen.queryByRole('heading', { level: 3, name: '[عنوان البصيرة]' })).toBeNull()
    );
    expect(screen.getByRole('heading', { level: 1, name: '[اسم عام]' })).toBeInTheDocument();
  });

  it('shows the blocked notice when the author blocked from a card is the profile itself', async () => {
    member({
      'PUT /blocks/rain_reader': { status: 204 },
    });
    render(<ProfileScreen handle="rain_reader" />);
    await screen.findByRole('heading', { level: 3, name: '[عنوان البصيرة]' });
    const cardMore = screen.getAllByRole('button', { name: 'المزيد' }).at(-1) as HTMLElement;
    await userEvent.click(cardMore);
    await userEvent.click(screen.getByRole('button', { name: /^احجب/ }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'احجب' }));
    expect(await screen.findByText(/حجبت هذا العضو/)).toBeInTheDocument();
  });

  it('ignores an answer that arrives after the page moved on', async () => {
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = member({
      'GET /u/rain_reader': async () => {
        await held;
        return { body: PROFILE };
      },
      'GET /u/other_one': { body: { ...PROFILE, handle: 'other_one', public_name: '[آخر]' } },
      'GET /u/other_one/posts': { body: page([]) },
    });
    const { rerender } = render(<ProfileScreen handle="rain_reader" />);
    await waitFor(() =>
      expect(api.requests.some((r) => r.url.endsWith('/u/rain_reader'))).toBe(true)
    );
    rerender(<ProfileScreen handle="other_one" />);
    expect(await screen.findByRole('heading', { level: 1, name: '[آخر]' })).toBeInTheDocument();
    release();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.getByRole('heading', { level: 1, name: '[آخر]' })).toBeInTheDocument();
  });
});

describe('formatMonth', () => {
  it('falls back to January 1970 for a missing part', () => {
    expect(formatMonth('2026')).toBe(formatMonth('2026-01'));
    expect(formatMonth('')).toBe(formatMonth('0-01'));
  });
});
