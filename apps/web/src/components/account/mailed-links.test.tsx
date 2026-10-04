import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { readSession } from '@/account/session';
import { apiError, mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { ForgotPasswordScreen } from './forgot-password-screen';
import { ResetPasswordScreen } from './reset-password-screen';
import { VerifyEmailScreen } from './verify-email-screen';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/',
}));

const TOKEN = 't'.repeat(43);

function openLink(path: string, token: string | null) {
  window.history.replaceState(null, '', token === null ? path : `${path}#token=${token}`);
}

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('ForgotPasswordScreen', () => {
  it('asks for a link and says what happens if the address has an account', async () => {
    const api = mockApi({
      'POST /auth/forgot-password': { status: 202, body: { status: 'accepted' } },
    });
    render(<ForgotPasswordScreen />);
    await userEvent.click(screen.getByRole('button', { name: 'أرسل الرابط' }));
    expect(screen.getByLabelText('البريد الإلكتروني')).toHaveFocus();
    await userEvent.type(screen.getByLabelText('البريد الإلكتروني'), 'reader@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'أرسل الرابط' }));
    expect(await screen.findByText(/إن كان لهذا البريد حساب/)).toBeInTheDocument();
    expect(await api.bodies('POST', '/auth/forgot-password')).toEqual([
      { email: 'reader@example.com' },
    ]);
    expect(screen.getByRole('link', { name: 'عد إلى الدخول' })).toHaveAttribute('href', '/signin');
  });

  it('shows a rate limit with how long to wait, and an address the API refused', async () => {
    mockApi({
      'POST /auth/forgot-password': apiError(429, 'RATE_LIMITED'),
    });
    render(<ForgotPasswordScreen />);
    await userEvent.type(screen.getByLabelText('البريد الإلكتروني'), 'reader@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'أرسل الرابط' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('محاولات كثيرة');
    mockApi({
      'POST /auth/forgot-password': apiError(422, 'VALIDATION_ERROR', {
        fields: [{ loc: ['body', 'email'], message: 'x', type: 'value_error' }],
      }),
    });
    await userEvent.click(screen.getByRole('button', { name: 'أرسل الرابط' }));
    await waitFor(() => expect(screen.getByLabelText('البريد الإلكتروني')).toBeInvalid());
  });
});

describe('VerifyEmailScreen', () => {
  it('spends the token only when the reader presses the button', async () => {
    openLink('/verify-email', TOKEN);
    const api = mockApi({
      'GET /auth/me': { body: USER },
      'POST /auth/verify-email': { body: { status: 'ok' } },
    });
    render(<VerifyEmailScreen />);
    const confirm = await screen.findByRole('button', { name: 'أكّد بريدي' });
    expect(window.location.hash).toBe('');
    expect(api.requests.some((request) => request.method === 'POST')).toBe(false);
    await userEvent.click(confirm);
    expect(await screen.findByText('تأكّد بريدك. شكرًا لك.')).toBeInTheDocument();
    expect(await api.bodies('POST', '/auth/verify-email')).toEqual([{ token: TOKEN }]);
    expect(screen.getByRole('link', { name: 'افتح ملفي' })).toHaveAttribute('href', '/me');
    await waitFor(() => expect(readSession().status).toBe('signed-in'));
  });

  it('offers a new link for a used one, with the signed-in address ready', async () => {
    openLink('/verify-email', TOKEN);
    const api = mockApi({
      'GET /auth/me': { body: USER },
      'POST /auth/verify-email': apiError(400, 'INVALID_TOKEN'),
      'POST /auth/resend-verification': { status: 202, body: { status: 'accepted' } },
    });
    render(<VerifyEmailScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'أكّد بريدي' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('هذا الرابط غير صالح');
    const field = screen.getByLabelText('البريد الإلكتروني');
    await waitFor(() => expect(field).toHaveValue('reader@example.com'));
    await userEvent.click(screen.getByRole('button', { name: 'أرسل الرابط' }));
    expect(await screen.findByText(/فستصله رسالة فيها رابط جديد/)).toBeInTheDocument();
    expect(await api.bodies('POST', '/auth/resend-verification')).toEqual([
      { email: 'reader@example.com' },
    ]);
  });

  it('explains a link without its token, and a server failure', async () => {
    openLink('/verify-email', null);
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    const { unmount } = render(<VerifyEmailScreen />);
    expect(await screen.findByText(/لم نجد رمز التأكيد/)).toBeInTheDocument();
    unmount();
    openLink('/verify-email', TOKEN);
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'POST /auth/verify-email': apiError(500, 'INTERNAL_ERROR'),
    });
    render(<VerifyEmailScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'أكّد بريدي' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('من جهتنا');
    expect(screen.getByRole('button', { name: 'أكّد بريدي' })).toBeEnabled();
  });
});

describe('ResetPasswordScreen', () => {
  it('sets a new password and leads to the sign-in', async () => {
    openLink('/reset-password', TOKEN);
    const api = mockApi({ 'POST /auth/reset-password': { body: { status: 'ok' } } });
    render(<ResetPasswordScreen />);
    const field = await screen.findByLabelText('كلمة المرور الجديدة');
    await userEvent.click(screen.getByRole('button', { name: 'احفظ كلمة المرور' }));
    expect(field).toHaveFocus();
    await userEvent.type(field, 'a new long password');
    await userEvent.click(screen.getByRole('button', { name: 'أظهر كلمة المرور' }));
    expect(field).toHaveAttribute('type', 'text');
    await userEvent.click(screen.getByRole('button', { name: 'احفظ كلمة المرور' }));
    expect(await screen.findByText(/حُفظت كلمة المرور الجديدة/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'ادخل' })).toHaveAttribute('href', '/signin');
    expect(await api.bodies('POST', '/auth/reset-password')).toEqual([
      { token: TOKEN, password: 'a new long password' },
    ]);
  });

  it('sends a used link to ask for a new one', async () => {
    openLink('/reset-password', TOKEN);
    mockApi({ 'POST /auth/reset-password': apiError(400, 'INVALID_TOKEN') });
    render(<ResetPasswordScreen />);
    await userEvent.type(
      await screen.findByLabelText('كلمة المرور الجديدة'),
      'a new long password'
    );
    await userEvent.click(screen.getByRole('button', { name: 'احفظ كلمة المرور' }));
    expect(await screen.findByRole('link', { name: 'اطلب رابطًا جديدًا' })).toHaveAttribute(
      'href',
      '/forgot-password'
    );
  });

  it('points at the password the API refused, and reports other failures', async () => {
    openLink('/reset-password', TOKEN);
    mockApi({
      'POST /auth/reset-password': apiError(422, 'VALIDATION_ERROR', {
        fields: [{ loc: ['body', 'password'], message: 'x', type: 'value_error' }],
      }),
    });
    render(<ResetPasswordScreen />);
    const field = await screen.findByLabelText('كلمة المرور الجديدة');
    await userEvent.type(field, 'a new long password');
    await userEvent.click(screen.getByRole('button', { name: 'احفظ كلمة المرور' }));
    await waitFor(() => expect(field).toHaveFocus());
    expect(field).toBeInvalid();
    mockApi({ 'POST /auth/reset-password': 'network-error' });
    await userEvent.click(screen.getByRole('button', { name: 'احفظ كلمة المرور' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('تعذّر الوصول إلى تبصرة');
  });

  it('explains a link without its token', async () => {
    openLink('/reset-password', null);
    render(<ResetPasswordScreen />);
    expect(await screen.findByText(/لم نجد رمز الاستعادة/)).toBeInTheDocument();
  });
});
