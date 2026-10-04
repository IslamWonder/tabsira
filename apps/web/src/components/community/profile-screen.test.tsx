import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
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
});
