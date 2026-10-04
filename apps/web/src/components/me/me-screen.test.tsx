import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { readSession } from '@/account/session';
import { writeConsentId } from '@/consent/cookie';
import { apiError, mockApi, type Route } from '@/test/api';
import { POLICY, PROFILE, RECORD, USER } from '@/test/fixtures';
import { MeScreen } from './me-screen';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/me',
}));

function signedIn(extra: Record<string, Route> = {}, user = USER): Record<string, Route> {
  return {
    'GET /auth/me': { body: user },
    'GET /profile': { body: PROFILE },
    'GET /consent/policy': { body: POLICY },
    ...extra,
  };
}

const section = (name: string) => screen.getByRole('region', { name });

describe('MeScreen for a guest', () => {
  it('keeps the device settings and the cookie choice, and invites to sign in', async () => {
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    render(<MeScreen />);
    expect(screen.getByRole('heading', { level: 1, name: 'ملفي' })).toBeInTheDocument();
    expect(within(section('حسابك')).getByText('نحمّل حسابك…')).toHaveAttribute('role', 'status');
    expect(await screen.findByRole('link', { name: 'ادخل' })).toHaveAttribute(
      'href',
      '/signin?next=/me'
    );
    expect(screen.getByRole('link', { name: 'أنشئ حسابًا' })).toHaveAttribute(
      'href',
      '/signup?next=/me'
    );
    expect(screen.getByRole('group', { name: 'المظهر' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'الحركة الزخرفية' })).toBeInTheDocument();
    expect(screen.queryByRole('switch', { name: 'التخصيص' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'بياناتك' })).toBeNull();
    expect(screen.getByText(/هذه علامات على التمرين والمواظبة لا على الإيمان/)).toBeInTheDocument();
    expect(within(section('ملفات تعريف الارتباط')).getByText('لم تختر بعد.')).toBeInTheDocument();
  });

  it('says when the account cannot be reached, and tries again', async () => {
    mockApi({ 'GET /auth/me': 'network-error' });
    render(<MeScreen />);
    expect(await screen.findByText(/تعذّر الوصول إلى حسابك الآن/)).toBeInTheDocument();
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(await screen.findByRole('link', { name: 'ادخل' })).toBeInTheDocument();
  });
});

describe('MeScreen signed in', () => {
  it('shows the account, its sections and signs out', async () => {
    mockApi(signedIn({ 'POST /auth/logout': { status: 204 } }));
    render(<MeScreen />);
    expect(await screen.findByText('[اسم القارئ]')).toBeInTheDocument();
    expect(screen.getByText('reader@example.com')).toBeInTheDocument();
    expect(screen.getByText('مؤكَّد')).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'أقسام ملفي' });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.getAttribute('href'))
    ).toEqual(['#account', '#about', '#settings', '#practice', '#data', '#cookies']);
    await userEvent.click(screen.getByRole('button', { name: 'اخرج' }));
    expect(await screen.findByText('خرجت من حسابك على هذا الجهاز.')).toBeInTheDocument();
    expect(readSession()).toEqual({ status: 'guest' });
  });

  it('offers a new verification link to an unverified address, and names Google', async () => {
    const api = mockApi(
      signedIn(
        { 'POST /auth/resend-verification': { status: 202, body: { status: 'accepted' } } },
        { ...USER, email_verified: false, providers: ['google'] }
      )
    );
    render(<MeScreen />);
    expect(await screen.findByText('لم يُؤكَّد بعد')).toBeInTheDocument();
    expect(screen.getByText('تدخل بحساب Google')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'أرسل رابط التأكيد مرة أخرى' }));
    expect(await screen.findByText(/فسيصله رابط جديد/)).toBeInTheDocument();
    expect(await api.bodies('POST', '/auth/resend-verification')).toEqual([
      { email: 'reader@example.com' },
    ]);
  });

  it('reports a failed resend', async () => {
    mockApi(
      signedIn(
        { 'POST /auth/resend-verification': apiError(429, 'RATE_LIMITED') },
        { ...USER, email_verified: false }
      )
    );
    render(<MeScreen />);
    await userEvent.click(
      await screen.findByRole('button', { name: 'أرسل رابط التأكيد مرة أخرى' })
    );
    expect(await screen.findByText(/محاولات كثيرة/)).toBeInTheDocument();
  });

  it('saves each answer of «عنك» at once, and undoes one the API refused', async () => {
    const api = mockApi(
      signedIn({ 'PATCH /profile': { body: { ...PROFILE, knowledge_level: 'advanced' } } })
    );
    render(<MeScreen />);
    const about = await screen.findByRole('region', { name: 'عنك' });
    expect(within(about).getByText(/نستخدم اختياراتك وبصائرك السابقة/)).toBeInTheDocument();
    await userEvent.click(within(about).getByRole('radio', { name: 'متقدم' }));
    expect(await within(about).findByText('حُفظ اختيارك.')).toBeInTheDocument();
    await userEvent.click(within(about).getByRole('checkbox', { name: 'التفكر' }));
    await userEvent.click(within(about).getByRole('radio', { name: '60 فأكثر' }));
    expect(await api.bodies('PATCH', '/profile')).toEqual([
      { knowledge_level: 'advanced' },
      { goals: ['reflection'] },
      { age_range: '60_plus' },
    ]);
    mockApi(signedIn({ 'PATCH /profile': apiError(500, 'INTERNAL_ERROR') }));
    await userEvent.click(within(about).getByRole('radio', { name: 'متخصص' }));
    expect(await within(about).findByRole('alert')).toBeInTheDocument();
    await waitFor(() =>
      expect(within(about).getByRole('radio', { name: 'متخصص' })).not.toBeChecked()
    );
  });

  it('records the consent switches and the private answers', async () => {
    const api = mockApi(
      signedIn({
        'POST /consents': {
          status: 201,
          body: { kind: 'memory', version: 'x', granted: false, created_at: 'x' },
        },
        'PATCH /profile': { body: { ...PROFILE, gender: 'woman' } },
      })
    );
    render(<MeScreen />);
    const memory = await screen.findByRole('switch', { name: 'الذاكرة' });
    await userEvent.click(memory);
    await waitFor(() => expect(memory).not.toBeChecked());
    await userEvent.click(screen.getByRole('radio', { name: 'أنثى' }));
    await waitFor(() => expect(screen.getByRole('radio', { name: 'أنثى' })).toBeChecked());
    expect(await api.bodies('POST', '/consents')).toEqual([
      { kind: 'memory', version: '2026-10-04', granted: false },
    ]);
    expect(screen.getByRole('switch', { name: 'التخصيص' })).toBeChecked();
    expect(screen.queryByRole('switch', { name: /الصوت/ })).toBeNull();
  });

  it('turns photo storage on, and records the religious background', async () => {
    const api = mockApi(
      signedIn({
        'POST /consents': {
          status: 201,
          body: { kind: 'photo_storage', version: 'x', granted: true, created_at: 'x' },
        },
        'PATCH /profile': { body: { ...PROFILE, religious_background: 'non_muslim' } },
      })
    );
    render(<MeScreen />);
    const photos = await screen.findByRole('switch', { name: 'حفظ صوري' });
    await userEvent.click(photos);
    await waitFor(() => expect(photos).toBeChecked());
    await userEvent.click(screen.getByRole('radio', { name: 'من غير المسلمين' }));
    expect(await api.bodies('PATCH', '/profile')).toEqual([{ religious_background: 'non_muslim' }]);
  });

  it('shows the latest answer when two saves cross', async () => {
    const answers: Array<() => void> = [];
    mockApi(
      signedIn({
        'PATCH /profile': async (request) => {
          const patch = (await request.json()) as Record<string, string>;
          return new Promise((resolve) => {
            answers.push(() => resolve({ body: { ...PROFILE, ...patch } }));
          });
        },
      })
    );
    render(<MeScreen />);
    const about = await screen.findByRole('region', { name: 'عنك' });
    await userEvent.click(within(about).getByRole('radio', { name: 'متقدم' }));
    await userEvent.click(within(about).getByRole('radio', { name: 'متخصص' }));
    await waitFor(() => expect(answers).toHaveLength(2));
    answers[1]?.();
    await waitFor(() => expect(within(about).getByRole('radio', { name: 'متخصص' })).toBeChecked());
    answers[0]?.();
    await waitFor(() => expect(within(about).getAllByText('حُفظ اختيارك.')).toHaveLength(1));
    expect(within(about).getByRole('radio', { name: 'متخصص' })).toBeChecked();
  });

  it('keeps a switch as it was when the API refuses, and rules out photos under 13', async () => {
    mockApi(
      signedIn({
        'GET /profile': { body: { ...PROFILE, age_range: 'under_13' } },
        'POST /consents': apiError(403, 'CONSENT_NOT_ALLOWED'),
      })
    );
    render(<MeScreen />);
    const photos = await screen.findByRole('switch', { name: 'حفظ صوري' });
    expect(photos).toBeDisabled();
    expect(photos).toHaveAccessibleDescription(/دون 13 عامًا/);
    const personal = screen.getByRole('switch', { name: 'التخصيص' });
    await userEvent.click(personal);
    expect(
      await screen.findByText(/لا نحفظ صور من صرّح بأنه دون 13 عامًا، فلا يمكن/)
    ).toBeInTheDocument();
    expect(personal).toBeChecked();
  });

  it('says when the profile cannot be read, and tries again', async () => {
    mockApi(signedIn({ 'GET /profile': apiError(500, 'INTERNAL_ERROR') }));
    render(<MeScreen />);
    expect(await screen.findByText(/حدث خطأ من جهتنا/)).toBeInTheDocument();
    mockApi(signedIn());
    await userEvent.click(
      within(section('الإعدادات')).getByRole('button', { name: 'أعد المحاولة' })
    );
    expect(await screen.findByRole('switch', { name: 'الذاكرة' })).toBeInTheDocument();
  });
});

describe('MeScreen data', () => {
  it('downloads everything the account owns as a file', async () => {
    mockApi(signedIn({ 'GET /account/export': { body: { consents: [], user: { id: 'x' } } } }));
    const createObjectURL = vi.fn(() => 'blob:export');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    render(<MeScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'نزّل بياناتي' }));
    expect(await screen.findByText('نُزّل الملف.')).toBeInTheDocument();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:export');
  });

  it('says when the export failed', async () => {
    mockApi(signedIn({ 'GET /account/export': apiError(401, 'UNAUTHORIZED') }));
    render(<MeScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'نزّل بياناتي' }));
    expect(await screen.findByText('انتهت جلستك. ادخل من جديد لتكمل.')).toBeInTheDocument();
  });

  it('opens the consent history once, newest first', async () => {
    const api = mockApi(
      signedIn({
        'GET /account/export': {
          body: {
            consents: [
              { kind: 'memory', version: 'v1', granted: true, created_at: '2026-10-01T08:00:00Z' },
              { kind: 'memory', version: 'v1', granted: false, created_at: '2026-10-03T08:00:00Z' },
            ],
          },
        },
      })
    );
    render(<MeScreen />);
    const summary = await screen.findByText('سجل الموافقات');
    await userEvent.click(summary);
    const items = await screen.findAllByRole('listitem');
    const history = items.filter((item) => item.textContent?.startsWith('الذاكرة'));
    expect(history.map((item) => item.textContent?.split(':')[1]?.trim().split(/\s/)[0])).toEqual([
      'سحبت',
      'وافقت',
    ]);
    await userEvent.click(summary);
    await userEvent.click(summary);
    expect(api.requests.filter((request) => request.url.endsWith('/account/export'))).toHaveLength(
      1
    );
  });

  it('shows an empty history and a failed one', async () => {
    mockApi(signedIn({ 'GET /account/export': { body: { consents: [] } } }));
    const { unmount } = render(<MeScreen />);
    await userEvent.click(await screen.findByText('سجل الموافقات'));
    expect(await screen.findByText('لا موافقات مسجّلة بعد.')).toBeInTheDocument();
    unmount();
    mockApi(signedIn({ 'GET /account/export': 'network-error' }));
    render(<MeScreen />);
    await userEvent.click(await screen.findByText('سجل الموافقات'));
    expect(await screen.findByText(/تعذّر الوصول إلى تبصرة/)).toBeInTheDocument();
  });

  it('deletes the account only after an in-page confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm');
    const api = mockApi(signedIn({ 'DELETE /account': apiError(500, 'INTERNAL_ERROR') }));
    render(<MeScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'احذف حسابي' }));
    const title = await screen.findByRole('heading', { name: 'هل تحذف حسابك نهائيًا؟' });
    await waitFor(() => expect(title).toHaveFocus());
    await userEvent.click(screen.getByRole('button', { name: 'تراجع' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'احذف حسابي' })).toHaveFocus());
    await userEvent.click(screen.getByRole('button', { name: 'احذف حسابي' }));
    await userEvent.click(screen.getByRole('button', { name: 'نعم، احذف حسابي نهائيًا' }));
    expect(await screen.findByText(/حدث خطأ من جهتنا/)).toBeInTheDocument();
    mockApi(signedIn({ 'DELETE /account': { status: 204 } }));
    await userEvent.click(screen.getByRole('button', { name: 'نعم، احذف حسابي نهائيًا' }));
    expect(await screen.findByText('حُذف حسابك وكل ما يخصّه.')).toBeInTheDocument();
    expect(readSession()).toEqual({ status: 'guest' });
    expect(confirm).not.toHaveBeenCalled();
    expect(api.requests.some((request) => request.method === 'DELETE')).toBe(true);
  });
});

describe('MeScreen cookies', () => {
  it('shows the recorded choice and reopens the consent screen', async () => {
    writeConsentId(RECORD.consent_id);
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /consent/policy': { body: POLICY },
      [`GET /consent/${RECORD.consent_id}`]: {
        body: { ...RECORD, decided_at: new Date().toISOString() },
      },
    });
    render(<MeScreen />);
    const cookies = section('ملفات تعريف الارتباط');
    await waitFor(() => expect(within(cookies).getByText('قياس الاستعمال')).toBeInTheDocument());
    expect(within(cookies).getAllByText('مسموح')).toHaveLength(1);
    expect(within(cookies).getAllByText('غير مسموح')).toHaveLength(1);
    expect(within(cookies).getByText(/^اخترت في/)).toBeInTheDocument();
    await userEvent.click(within(cookies).getByRole('button', { name: 'غيّر اختياراتي' }));
    const { readConsent } = await import('@/consent/store');
    expect(readConsent().settingsOpen).toBe(true);
  });
});
