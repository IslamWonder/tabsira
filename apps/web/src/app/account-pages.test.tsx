import { render, screen } from '@testing-library/react';
import type { Metadata } from 'next';
import { describe, expect, it, vi } from 'vitest';
import ForgotPasswordPage, { metadata as forgotMetadata } from './forgot-password/page';
import ResetPasswordPage, { metadata as resetMetadata } from './reset-password/page';
import SignInPage, { metadata as signInMetadata } from './signin/page';
import SignUpPage, { metadata as signUpMetadata } from './signup/page';
import VerifyEmailPage, { metadata as verifyMetadata } from './verify-email/page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/',
}));

describe('the account pages', () => {
  it.each<[string, Metadata, string]>([
    ['/signin', signInMetadata, 'الدخول'],
    ['/signup', signUpMetadata, 'إنشاء حساب'],
    ['/verify-email', verifyMetadata, 'تأكيد البريد'],
    ['/forgot-password', forgotMetadata, 'استعادة كلمة المرور'],
    ['/reset-password', resetMetadata, 'كلمة مرور جديدة'],
  ])('%s is private, titled and canonical', (path, metadata, title) => {
    expect(metadata.title).toBe(title);
    expect(metadata.alternates?.canonical).toBe(path);
    expect(metadata.robots).toEqual({ index: false, follow: false });
    expect(String(metadata.description).length).toBeLessThanOrEqual(165);
  });

  it('signs in towards a safe next path, with a known Google error only', async () => {
    render(
      await SignInPage({
        params: Promise.resolve({}),
        searchParams: Promise.resolve({ next: '//evil.example', error: 'google_failed' }),
      } as PageProps<'/signin'>)
    );
    expect(screen.getByRole('alert')).toHaveTextContent('لم نتمكن من إتمام الدخول بحساب Google');
    expect(screen.getByRole('link', { name: 'أنشئ حسابًا' })).toHaveAttribute(
      'href',
      '/signup?next=%2Fme'
    );
  });

  it('ignores an unknown error code', async () => {
    render(
      await SignInPage({
        params: Promise.resolve({}),
        searchParams: Promise.resolve({ error: 'toString' }),
      } as PageProps<'/signin'>)
    );
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders the other screens', async () => {
    render(
      await SignUpPage({
        params: Promise.resolve({}),
        searchParams: Promise.resolve({ next: '/world' }),
      } as PageProps<'/signup'>)
    );
    expect(screen.getByRole('heading', { level: 1, name: 'أنشئ حسابك' })).toBeInTheDocument();
    for (const [Page, title] of [
      [VerifyEmailPage, 'تأكيد بريدك'],
      [ForgotPasswordPage, 'استعادة كلمة المرور'],
      [ResetPasswordPage, 'كلمة مرور جديدة'],
    ] as const) {
      const { unmount } = render(<Page />);
      expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument();
      unmount();
    }
  });
});
