import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readSession } from '@/account/session';
import { apiError, mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { SignInScreen } from './sign-in-screen';

const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router, usePathname: () => '/signin' }));

const GOOGLE = {
  body: {
    providers: [
      { id: 'password', available: true },
      { id: 'google', available: true },
    ],
  },
};
const NO_GOOGLE = { body: { providers: [{ id: 'password', available: true }] } };

beforeEach(() => {
  router.replace.mockReset();
});

async function fill(email: string, password: string) {
  if (email) await userEvent.type(screen.getByLabelText('البريد الإلكتروني'), email);
  if (password) await userEvent.type(screen.getByLabelText('كلمة المرور'), password);
  await userEvent.click(screen.getByRole('button', { name: 'ادخل' }));
}

describe('SignInScreen', () => {
  it('signs in and goes where it was asked to', async () => {
    const api = mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /auth/providers': NO_GOOGLE,
      'POST /auth/login': { body: USER },
    });
    render(<SignInScreen next="/world" />);
    expect(screen.getByRole('heading', { level: 1, name: 'ادخل إلى تبصرة' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'تبصرة' })).toBeInTheDocument();
    await fill('reader@example.com', 'a long password');
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/world'));
    expect(await api.bodies('POST', '/auth/login')).toEqual([
      { email: 'reader@example.com', password: 'a long password' },
    ]);
    expect(readSession()).toEqual({ status: 'signed-in', user: USER });
    expect(screen.getByRole('link', { name: 'أنشئ حسابًا' })).toHaveAttribute(
      'href',
      '/signup?next=%2Fworld'
    );
  });

  it('checks the fields first and puts focus on the first one to fix', async () => {
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED'), 'GET /auth/providers': NO_GOOGLE });
    render(<SignInScreen next="/me" />);
    await fill('', '');
    expect(screen.getByLabelText('البريد الإلكتروني')).toHaveFocus();
    expect(screen.getByLabelText('البريد الإلكتروني')).toHaveAccessibleDescription(
      'اكتب بريدك الإلكتروني.'
    );
    await fill('reader@example.com', '');
    expect(screen.getByLabelText('كلمة المرور')).toHaveFocus();
  });

  it('says plainly why a sign-in failed', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /auth/providers': NO_GOOGLE,
      'POST /auth/login': apiError(401, 'INVALID_CREDENTIALS'),
    });
    render(<SignInScreen next="/me" />);
    await fill('reader@example.com', 'wrong');
    expect(await screen.findByRole('alert')).toHaveTextContent('لا يتطابقان');
  });

  it('points at the address when the API refuses its form', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /auth/providers': NO_GOOGLE,
      'POST /auth/login': apiError(422, 'VALIDATION_ERROR', {
        fields: [{ loc: ['body', 'email'], message: 'x', type: 'value_error' }],
      }),
    });
    render(<SignInScreen next="/me" />);
    await fill('reader@example.co', 'x');
    await waitFor(() => expect(screen.getByLabelText('البريد الإلكتروني')).toHaveFocus());
    expect(screen.getByLabelText('البريد الإلكتروني')).toBeInvalid();
  });

  it('offers Google when it is configured, and shows a failed Google sign-in', async () => {
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED'), 'GET /auth/providers': GOOGLE });
    render(<SignInScreen next="/me" googleError="google_denied" />);
    expect(screen.getByRole('alert')).toHaveTextContent('ألغيت الدخول في صفحة Google');
    const google = await screen.findByRole('link', { name: /تابع بحساب\s+Google/ });
    expect(google).toHaveAttribute('href', 'https://api.tabsira.test/auth/google/start?next=%2Fme');
    expect(screen.getByText('أو بالبريد الإلكتروني')).toBeInTheDocument();
  });

  it('says who is signed in instead of the form', async () => {
    mockApi({ 'GET /auth/me': { body: USER }, 'POST /auth/logout': { status: 204 } });
    render(<SignInScreen next="/me" />);
    expect(await screen.findByText('أنت داخل باسم [اسم القارئ].')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'افتح ملفي' })).toHaveAttribute('href', '/me');
    await userEvent.click(screen.getByRole('button', { name: 'اخرج' }));
    expect(await screen.findByLabelText('البريد الإلكتروني')).toBeInTheDocument();
  });
});
