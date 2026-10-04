import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { readSession } from '@/account/session';
import { apiError, mockApi, type Route } from '@/test/api';
import { USER } from '@/test/fixtures';
import { LEGAL } from '@/test/legal';
import { SignUpScreen } from './sign-up-screen';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/signup',
}));

const GOOGLE = {
  body: {
    providers: [
      { id: 'password', available: true },
      { id: 'google', available: true },
    ],
  },
};

function routes(extra: Record<string, Route> = {}): Record<string, Route> {
  return {
    'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
    'GET /auth/providers': GOOGLE,
    'GET /legal': { body: LEGAL },
    ...extra,
  };
}

async function fill() {
  await userEvent.type(screen.getByLabelText('الاسم الذي نناديك به'), '  قارئ   جديد ');
  await userEvent.type(screen.getByLabelText('البريد الإلكتروني'), 'new@example.com');
  await userEvent.type(screen.getByLabelText('كلمة المرور'), 'a long password');
}

const submit = () => screen.getByRole('button', { name: 'أنشئ الحساب' });
const box = () => screen.getByRole('checkbox', { name: /أوافق على شروط الاستخدام/ });

describe('SignUpScreen', () => {
  it('keeps both ways in closed until the terms are accepted (decision 35)', async () => {
    mockApi(routes());
    render(<SignUpScreen next="/me" />);
    await waitFor(() => expect(box()).toBeEnabled());
    expect(box()).not.toBeChecked();
    expect(submit()).toBeDisabled();
    const google = await screen.findByRole('button', { name: /تابع بحساب\s+Google/ });
    expect(google).toBeDisabled();
    expect(screen.getByRole('link', { name: /شروط الاستخدام/ })).toHaveAttribute('href', '/terms');
    expect(screen.getByRole('link', { name: /سياسة الخصوصية/ })).toHaveAttribute(
      'target',
      '_blank'
    );
    await userEvent.click(box());
    expect(submit()).toBeEnabled();
    const link = screen.getByRole('link', { name: /تابع بحساب\s+Google/ });
    // The acceptance never travels in the link (security review): the tick stays in this tab.
    expect(link).toHaveAttribute('href', 'https://api.tabsira.test/auth/google/start?next=%2Fme');
    link.addEventListener('click', (event) => event.preventDefault());
    await userEvent.click(link);
    expect(JSON.parse(window.sessionStorage.getItem('tabsira.legal.tick') ?? '{}')).toMatchObject({
      terms_version: '2026-10-04',
      privacy_version: '2026-10-04',
    });
  });

  it('creates the account with the accepted versions and says what comes next', async () => {
    const api = mockApi(routes({ 'POST /auth/signup': { status: 201, body: USER } }));
    render(<SignUpScreen next="/world" />);
    await waitFor(() => expect(box()).toBeEnabled());
    await fill();
    await userEvent.click(box());
    await userEvent.click(submit());
    expect(await screen.findByRole('heading', { name: 'أُنشئ حسابك' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('reader@example.com');
    expect(screen.getByRole('link', { name: 'تابع' })).toHaveAttribute('href', '/world');
    expect(await api.bodies('POST', '/auth/signup')).toEqual([
      {
        email: 'new@example.com',
        password: 'a long password',
        display_name: 'قارئ جديد',
        accepted_terms_version: '2026-10-04',
        accepted_privacy_version: '2026-10-04',
      },
    ]);
    expect(readSession().status).toBe('signed-in');
  });

  it('checks every field before sending', async () => {
    const api = mockApi(routes());
    render(<SignUpScreen next="/me" />);
    await waitFor(() => expect(box()).toBeEnabled());
    await userEvent.click(box());
    await userEvent.click(submit());
    expect(screen.getByLabelText('الاسم الذي نناديك به')).toHaveFocus();
    await userEvent.type(screen.getByLabelText('الاسم الذي نناديك به'), 'قارئ');
    await userEvent.type(screen.getByLabelText('البريد الإلكتروني'), 'new@example.com');
    await userEvent.type(screen.getByLabelText('كلمة المرور'), 'short');
    await userEvent.click(submit());
    expect(screen.getByLabelText('كلمة المرور')).toHaveFocus();
    expect(screen.getByText('كلمة المرور قصيرة: عشرة أحرف على الأقل.')).toBeInTheDocument();
    expect(api.requests.some((request) => request.method === 'POST')).toBe(false);
  });

  it.each([
    ['display_name', 'الاسم الذي نناديك به'],
    ['email', 'البريد الإلكتروني'],
    ['password', 'كلمة المرور'],
  ])('points at the %s field the API refused', async (field, label) => {
    mockApi(
      routes({
        'POST /auth/signup': apiError(422, 'VALIDATION_ERROR', {
          fields: [{ loc: ['body', field], message: 'x', type: 'value_error' }],
        }),
      })
    );
    render(<SignUpScreen next="/me" />);
    await waitFor(() => expect(box()).toBeEnabled());
    await fill();
    await userEvent.click(box());
    await userEvent.click(submit());
    await waitFor(() => expect(screen.getByLabelText(label)).toHaveFocus());
  });

  it('says when the address already has an account', async () => {
    mockApi(routes({ 'POST /auth/signup': apiError(409, 'EMAIL_TAKEN') }));
    render(<SignUpScreen next="/me" />);
    await waitFor(() => expect(box()).toBeEnabled());
    await fill();
    await userEvent.click(box());
    await userEvent.click(submit());
    expect(await screen.findByRole('alert')).toHaveTextContent('لهذا البريد حساب من قبل');
  });

  it('asks again when the texts changed while the form was open', async () => {
    const api = mockApi(
      routes({ 'POST /auth/signup': apiError(422, 'legal_acceptance_required') })
    );
    render(<SignUpScreen next="/me" />);
    await waitFor(() => expect(box()).toBeEnabled());
    await fill();
    await userEvent.click(box());
    await userEvent.click(submit());
    expect(await screen.findByRole('alert')).toHaveTextContent('تغيّرت شروط الاستخدام');
    expect(box()).not.toBeChecked();
    await waitFor(() =>
      expect(api.requests.filter((request) => request.url.endsWith('/legal'))).toHaveLength(2)
    );
  });

  it('cannot create an account while the texts cannot be read, and offers to retry', async () => {
    const api = mockApi(routes({ 'GET /legal': 'network-error' }));
    render(<SignUpScreen next="/me" />);
    expect(await screen.findByText(/تعذّر تحميل نسخة الشروط/)).toBeInTheDocument();
    expect(box()).toBeDisabled();
    expect(submit()).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(api.requests.filter((request) => request.url.endsWith('/legal'))).toHaveLength(2);
  });

  it('says who is signed in instead of the form', async () => {
    mockApi(routes({ 'GET /auth/me': { body: USER } }));
    render(<SignUpScreen next="/me" />);
    expect(await screen.findByText('أنت داخل باسم [اسم القارئ].')).toBeInTheDocument();
  });
});
