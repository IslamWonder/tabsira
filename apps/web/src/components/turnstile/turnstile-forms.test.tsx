import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ForgotPasswordScreen } from '@/components/account/forgot-password-screen';
import { SignInScreen } from '@/components/account/sign-in-screen';
import { SignUpScreen } from '@/components/account/sign-up-screen';
import { VerifyEmailScreen } from '@/components/account/verify-email-screen';
import { SupportForm } from '@/components/legal/support-form';
import { messages } from '@/messages';
import { legalMessages } from '@/messages/legal';
import { apiError, mockApi, type Route } from '@/test/api';
import { USER } from '@/test/fixtures';
import { LEGAL } from '@/test/legal';

/*
 * Decision 56: the five forms send the Turnstile token in the header
 * CF-Turnstile-Response, reset the widget after each submit, and nothing at
 * all happens when the site has no key.
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/',
}));
vi.mock('@/analytics/events', () => ({ track: vi.fn() }));
vi.mock('@/lib/turnstile', async (original) => ({
  ...(await original<typeof import('@/lib/turnstile')>()),
  loadTurnstile: vi.fn(async () => undefined),
}));

const KEY = '1x00000000000000000000AA';
const HEADER = 'CF-Turnstile-Response';
const FAILED = messages.errors.turnstileFailed;

let issued = 0;
const widgetReset = vi.fn();

beforeEach(() => {
  issued = 0;
  widgetReset.mockReset();
  // The check solves at once with a new single-use token each time, and again after a reset.
  window.turnstile = {
    render: (_box, options) => {
      options.callback?.(`tok-${++issued}`);
      widgetReset.mockImplementation(() => options.callback?.(`tok-${++issued}`));
      return 'w1';
    },
    reset: widgetReset,
    remove: vi.fn(),
  };
});

afterEach(() => {
  delete window.turnstile;
  window.history.replaceState(null, '', '/');
});

const ME_AND_PROVIDERS: Record<string, Route> = {
  'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
  'GET /auth/providers': { body: { providers: [{ id: 'password', available: true }] } },
};

function headerOf(api: ReturnType<typeof mockApi>, method: string, path: string) {
  const request = api.requests.find(
    (candidate) => candidate.method === method && new URL(candidate.url).pathname === path
  );
  return request?.headers.get(HEADER) ?? null;
}

describe('sign in', () => {
  async function signIn() {
    await userEvent.type(screen.getByLabelText('البريد الإلكتروني'), 'reader@example.com');
    await userEvent.type(screen.getByLabelText('كلمة المرور'), 'a long password');
    await userEvent.click(screen.getByRole('button', { name: 'ادخل' }));
  }

  it('sends the token, then resets the widget', async () => {
    const api = mockApi({ ...ME_AND_PROVIDERS, 'POST /auth/login': { body: USER } });
    render(<SignInScreen next="/me" turnstileSiteKey={KEY} />);
    await signIn();
    await waitFor(() => expect(widgetReset).toHaveBeenCalledWith('w1'));
    expect(headerOf(api, 'POST', '/auth/login')).toBe('tok-1');
  });

  it('shows no widget and sends no header without a key', async () => {
    const api = mockApi({ ...ME_AND_PROVIDERS, 'POST /auth/login': { body: USER } });
    render(<SignInScreen next="/me" />);
    expect(screen.queryByRole('group', { name: messages.auth.turnstile.label })).toBeNull();
    await signIn();
    await waitFor(() => expect(api.requests.some((r) => r.method === 'POST')).toBe(true));
    expect(headerOf(api, 'POST', '/auth/login')).toBeNull();
    expect(widgetReset).not.toHaveBeenCalled();
  });

  it('says the check failed on a 403 turnstile_failed, and has a fresh token for the retry', async () => {
    const api = mockApi({
      ...ME_AND_PROVIDERS,
      'POST /auth/login': apiError(403, 'turnstile_failed'),
    });
    render(<SignInScreen next="/me" turnstileSiteKey={KEY} />);
    await signIn();
    expect(await screen.findByRole('alert')).toHaveTextContent(FAILED);
    expect(widgetReset).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: 'ادخل' }));
    await waitFor(() => expect(api.requests.filter((r) => r.method === 'POST')).toHaveLength(2));
    const second = api.requests.filter((r) => r.method === 'POST')[1];
    expect(second?.headers.get(HEADER)).toBe('tok-2');
  });
});

describe('sign up', () => {
  const routes: Record<string, Route> = {
    ...ME_AND_PROVIDERS,
    'GET /legal': { body: LEGAL },
  };

  async function signUp() {
    await userEvent.type(screen.getByLabelText('الاسم الكامل'), 'قارئ جديد');
    await userEvent.type(screen.getByLabelText('البريد الإلكتروني'), 'new@example.com');
    await userEvent.type(screen.getByLabelText('كلمة المرور'), 'a long password');
    const box = screen.getByRole('checkbox', { name: /أوافق على شروط الاستخدام/ });
    await waitFor(() => expect(box).toBeEnabled());
    await userEvent.click(box);
    await userEvent.click(screen.getByRole('button', { name: 'أنشئ الحساب' }));
  }

  it('sends the token, then resets the widget', async () => {
    const api = mockApi({ ...routes, 'POST /auth/signup': { status: 201, body: USER } });
    render(<SignUpScreen next="/me" turnstileSiteKey={KEY} />);
    await signUp();
    await waitFor(() => expect(widgetReset).toHaveBeenCalledWith('w1'));
    expect(headerOf(api, 'POST', '/auth/signup')).toBe('tok-1');
  });

  it('sends no header without a key', async () => {
    const api = mockApi({ ...routes, 'POST /auth/signup': { status: 201, body: USER } });
    render(<SignUpScreen next="/me" />);
    await signUp();
    await waitFor(() => expect(api.requests.some((r) => r.method === 'POST')).toBe(true));
    expect(headerOf(api, 'POST', '/auth/signup')).toBeNull();
  });

  it('says the check failed on a 403 turnstile_failed', async () => {
    mockApi({ ...routes, 'POST /auth/signup': apiError(403, 'turnstile_failed') });
    render(<SignUpScreen next="/me" turnstileSiteKey={KEY} />);
    await signUp();
    expect(await screen.findByRole('alert')).toHaveTextContent(FAILED);
    expect(widgetReset).toHaveBeenCalledTimes(1);
  });
});

describe('forgot password', () => {
  async function ask() {
    await userEvent.type(screen.getByLabelText('البريد الإلكتروني'), 'reader@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'أرسل الرابط' }));
  }

  it('sends the token, then resets the widget', async () => {
    const api = mockApi({
      'POST /auth/forgot-password': { status: 202, body: { status: 'accepted' } },
    });
    render(<ForgotPasswordScreen turnstileSiteKey={KEY} />);
    await ask();
    expect(await screen.findByText(/إن كان لهذا البريد حساب/)).toBeInTheDocument();
    expect(headerOf(api, 'POST', '/auth/forgot-password')).toBe('tok-1');
    expect(widgetReset).toHaveBeenCalledWith('w1');
  });

  it('sends no header without a key', async () => {
    const api = mockApi({
      'POST /auth/forgot-password': { status: 202, body: { status: 'accepted' } },
    });
    render(<ForgotPasswordScreen />);
    await ask();
    expect(await screen.findByText(/إن كان لهذا البريد حساب/)).toBeInTheDocument();
    expect(headerOf(api, 'POST', '/auth/forgot-password')).toBeNull();
  });

  it('says the check failed on a 403 turnstile_failed', async () => {
    mockApi({ 'POST /auth/forgot-password': apiError(403, 'turnstile_failed') });
    render(<ForgotPasswordScreen turnstileSiteKey={KEY} />);
    await ask();
    expect(await screen.findByRole('alert')).toHaveTextContent(FAILED);
  });
});

describe('resend the verification link', () => {
  const routes: Record<string, Route> = {
    'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
    'POST /auth/resend-verification': { status: 202, body: { status: 'accepted' } },
  };

  async function resend() {
    await userEvent.type(screen.getByLabelText('البريد الإلكتروني'), 'reader@example.com');
    await userEvent.click(screen.getByRole('button', { name: messages.auth.verify.resend }));
  }

  it('sends the token, then resets the widget', async () => {
    const api = mockApi(routes);
    render(<VerifyEmailScreen turnstileSiteKey={KEY} />);
    await resend();
    await waitFor(() => expect(widgetReset).toHaveBeenCalledWith('w1'));
    expect(headerOf(api, 'POST', '/auth/resend-verification')).toBe('tok-1');
  });

  it('sends no header without a key', async () => {
    const api = mockApi(routes);
    render(<VerifyEmailScreen />);
    await resend();
    await waitFor(() => expect(api.requests.some((r) => r.method === 'POST')).toBe(true));
    expect(headerOf(api, 'POST', '/auth/resend-verification')).toBeNull();
  });
});

describe('support form', () => {
  const T = legalMessages().support;

  async function send() {
    await userEvent.type(screen.getByLabelText(/بريدك الإلكتروني/), 'ahmad@example.com');
    await userEvent.selectOptions(screen.getByLabelText(/موضوع الرسالة/), 'bug');
    await userEvent.type(screen.getByLabelText(/رسالتك/), 'مرحبًا، أحتاج مساعدة في حسابي من فضلكم.');
    await userEvent.click(screen.getByRole('button', { name: T.form.send }));
  }

  it('sends the token, then resets the widget', async () => {
    const api = mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'POST /support': { status: 202 },
    });
    render(<SupportForm turnstileSiteKey={KEY} />);
    await send();
    expect(await screen.findByText(T.result.sent)).toBeInTheDocument();
    expect(headerOf(api, 'POST', '/support')).toBe('tok-1');
    expect(widgetReset).toHaveBeenCalledWith('w1');
  });

  it('sends no header without a key', async () => {
    const api = mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'POST /support': { status: 202 },
    });
    render(<SupportForm />);
    await send();
    expect(await screen.findByText(T.result.sent)).toBeInTheDocument();
    expect(headerOf(api, 'POST', '/support')).toBeNull();
  });

  it('says the check failed on a 403 turnstile_failed, and that nothing was sent', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'POST /support': apiError(403, 'turnstile_failed'),
    });
    render(<SupportForm turnstileSiteKey={KEY} />);
    await send();
    expect(await screen.findByText(T.result.turnstileFailed)).toBeInTheDocument();
    expect(widgetReset).toHaveBeenCalledTimes(1);
  });
});
