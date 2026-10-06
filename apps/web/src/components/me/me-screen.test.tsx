import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CONSENT_TEXT_VERSION } from '@/account/profile';
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
    'GET /me/public-identity': {
      body: { handle: null, public_name: null, public_full_name: false },
    },
    'GET /blocks': { body: [] },
    'GET /geo/countries': { body: COUNTRIES },
    ...extra,
  };
}

const country = (iso2: string, name: string, label: string) => ({
  iso2,
  iso3: null,
  name,
  name_ar: label === name ? null : label,
  label,
  capital: null,
  continent: null,
  flag_emoji: null,
  population: null,
});
// In GeoNames' English order; the select lists them by the name shown.
const COUNTRIES = [
  country('FR', 'France', 'فرنسا'),
  country('SA', 'Saudi Arabia', 'السعودية'),
  country('TN', 'Tunisia', 'تونس'),
];

const section = (name: string) => screen.getByRole('region', { name });

/** «ملفي» opened at one of its sections (`/me#data`), as a link or a shared address would. */
function renderAt(id?: string) {
  window.history.replaceState(null, '', id === undefined ? '/me' : `/me#${id}`);
  return render(<MeScreen />);
}

/** A tap on an entry of the menu: the address names the section. */
const go = (id: string) =>
  act(() => {
    window.history.pushState(null, '', `/me#${id}`);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

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
    go('appearance');
    expect(screen.getByRole('group', { name: 'المظهر' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'الحركة الزخرفية' })).toBeInTheDocument();
    go('personalization');
    expect(screen.queryByRole('switch', { name: 'التخصيص' })).toBeNull();
    expect(
      within(section('التخصيص والخصوصية')).getByText(/خيارات لحسابك، تجدها هنا بعد الدخول/)
    ).toBeInTheDocument();
    // A guest has no data to export: the entry is not offered, and its address opens nothing.
    go('data');
    expect(screen.queryByRole('region', { name: 'بياناتك' })).toBeNull();
    go('practice');
    expect(screen.getByText(/هذه علامات على التمرين والمواظبة لا على الإيمان/)).toBeInTheDocument();
    expect(within(section('تمرينك')).getByRole('link', { name: 'افتح تمرينك' })).toHaveAttribute(
      'href',
      '/sky'
    );
    go('cookies');
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
    // The menu beside the section (from tablet up) and the phone's hub list the same entries.
    for (const nav of screen.getAllByRole('navigation', { name: 'أقسام ملفي' })) {
      expect(
        within(nav)
          .getAllByRole('link')
          .map((link) => link.getAttribute('href'))
      ).toEqual([
        '#account',
        '#about',
        '#identity',
        '#appearance',
        '#personalization',
        '#practice',
        '#app',
        '#data',
        '#cookies',
      ]);
    }
    await userEvent.click(screen.getByRole('button', { name: 'اخرج' }));
    expect(await screen.findByText('خرجت من حسابك على هذا الجهاز.')).toBeInTheDocument();
    expect(readSession()).toEqual({ status: 'guest' });
  });

  it('sends an unverified address to /verify-email for a new link, and names Google', async () => {
    const api = mockApi(signedIn({}, { ...USER, email_verified: false, providers: ['google'] }));
    render(<MeScreen />);
    expect(await screen.findByText('لم يُؤكَّد بعد')).toBeInTheDocument();
    expect(screen.getByText('تدخل بحساب Google')).toBeInTheDocument();
    // The Turnstile check lives on that page; /me never calls the route itself (decision 56).
    expect(screen.getByRole('link', { name: 'أرسل رابط التأكيد مرة أخرى' })).toHaveAttribute(
      'href',
      '/verify-email'
    );
    expect(api.requests.some((request) => request.url.includes('resend-verification'))).toBe(false);
  });

  it('saves each answer of «عنك» at once, and undoes one the API refused', async () => {
    const api = mockApi(
      signedIn({ 'PATCH /profile': { body: { ...PROFILE, knowledge_level: 'advanced' } } })
    );
    renderAt('about');
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
    renderAt('personalization');
    const memory = await screen.findByRole('switch', { name: 'الذاكرة' });
    await userEvent.click(memory);
    await waitFor(() => expect(memory).not.toBeChecked());
    await userEvent.click(screen.getByRole('radio', { name: 'أنثى' }));
    await waitFor(() => expect(screen.getByRole('radio', { name: 'أنثى' })).toBeChecked());
    expect(await api.bodies('POST', '/consents')).toEqual([
      { kind: 'memory', version: CONSENT_TEXT_VERSION, granted: false },
    ]);
    expect(screen.getByRole('switch', { name: 'التخصيص' })).toBeChecked();
    go('appearance');
    expect(screen.getByRole('switch', { name: 'المؤثر الصوتي' })).toBeChecked();
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
    renderAt('personalization');
    const photos = await screen.findByRole('switch', { name: 'حفظ صوري' });
    await userEvent.click(photos);
    await waitFor(() => expect(photos).toBeChecked());
    await userEvent.click(screen.getByRole('radio', { name: 'من غير المسلمين' }));
    expect(await api.bodies('PATCH', '/profile')).toEqual([{ religious_background: 'non_muslim' }]);
  });

  it('declares a country, clears it, and shows it publicly only by its own switch', async () => {
    const api = mockApi(
      signedIn({
        'PATCH /profile': async (request) => ({
          body: { ...PROFILE, ...((await request.json()) as object) },
        }),
        'POST /consents': {
          status: 201,
          body: { kind: 'public_country', version: 'x', granted: true, created_at: 'x' },
        },
      })
    );
    renderAt('personalization');
    const select = await screen.findByRole('combobox', { name: 'بلدي' });
    expect(
      within(select)
        .getAllByRole('option')
        .map((option) => option.textContent)
    ).toEqual(['لا أريد التحديد', 'السعودية', 'تونس', 'فرنسا']);
    expect(select).toHaveValue('');
    const shown = screen.getByRole('switch', { name: 'أظهر بلدي في ملفي العام' });
    expect(shown).not.toBeChecked();
    await userEvent.selectOptions(select, 'TN');
    await waitFor(() => expect(select).toHaveValue('TN'));
    await userEvent.selectOptions(select, '');
    await waitFor(() => expect(select).toHaveValue(''));
    await userEvent.click(shown);
    await waitFor(() => expect(shown).toBeChecked());
    expect(await api.bodies('PATCH', '/profile')).toEqual([{ country: 'TN' }, { country: null }]);
    expect(await api.bodies('POST', '/consents')).toEqual([
      { kind: 'public_country', version: CONSENT_TEXT_VERSION, granted: true },
    ]);
  });

  it('offers to read the countries again, and rules out showing one under 13', async () => {
    let calls = 0;
    let release: () => void = () => undefined;
    mockApi(
      signedIn({
        'GET /profile': { body: { ...PROFILE, age_range: 'under_13' } },
        'GET /geo/countries': () =>
          ++calls === 1
            ? apiError(500, 'INTERNAL_ERROR')
            : new Promise((resolve) => {
                release = () => resolve({ body: COUNTRIES });
              }),
      })
    );
    renderAt('personalization');
    expect(await screen.findByText('تعذّر تحميل قائمة البلدان الآن.')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'أظهر بلدي في ملفي العام' })).toBeDisabled();
    expect(
      screen.getByRole('switch', { name: 'أظهر بلدي في ملفي العام' })
    ).toHaveAccessibleDescription(/لا نُظهر بلد من صرّح بأنه دون 13 عامًا/);
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(await screen.findByText('نحمّل قائمة البلدان…')).toBeInTheDocument();
    await waitFor(() => expect(calls).toBe(2));
    release();
    expect(await screen.findByRole('combobox', { name: 'بلدي' })).toBeInTheDocument();
  });

  it('drops the country list when it arrives after the settings closed', async () => {
    let release: () => void = () => undefined;
    const api = mockApi(
      signedIn({
        'GET /geo/countries': () =>
          new Promise((resolve) => {
            release = () => resolve({ body: COUNTRIES });
          }),
      })
    );
    const view = renderAt('personalization');
    expect(await screen.findByText('نحمّل قائمة البلدان…')).toBeInTheDocument();
    view.unmount();
    release();
    await waitFor(() =>
      expect(api.requests.filter((r) => r.url.endsWith('/geo/countries'))).toHaveLength(1)
    );
    expect(screen.queryByRole('combobox')).toBeNull();
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
    renderAt('about');
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
    renderAt('personalization');
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
    renderAt('personalization');
    expect(await screen.findByText(/حدث خطأ من جهتنا/)).toBeInTheDocument();
    mockApi(signedIn());
    await userEvent.click(
      within(section('التخصيص والخصوصية')).getByRole('button', { name: 'أعد المحاولة' })
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
    renderAt('data');
    await userEvent.click(await screen.findByRole('button', { name: 'نزّل بياناتي' }));
    expect(await screen.findByText('نُزّل الملف.')).toBeInTheDocument();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:export');
  });

  it('says when the export failed', async () => {
    mockApi(signedIn({ 'GET /account/export': apiError(401, 'UNAUTHORIZED') }));
    renderAt('data');
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
    renderAt('data');
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
    const { unmount } = renderAt('data');
    await userEvent.click(await screen.findByText('سجل الموافقات'));
    expect(await screen.findByText('لا موافقات مسجّلة بعد.')).toBeInTheDocument();
    unmount();
    mockApi(signedIn({ 'GET /account/export': 'network-error' }));
    renderAt('data');
    await userEvent.click(await screen.findByText('سجل الموافقات'));
    expect(await screen.findByText(/تعذّر الوصول إلى تبصرة/)).toBeInTheDocument();
  });

  it('deletes the account only after an in-page confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm');
    const api = mockApi(signedIn({ 'DELETE /account': apiError(500, 'INTERNAL_ERROR') }));
    renderAt('data');
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
    renderAt('cookies');
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

describe('MeScreen menu', () => {
  it('opens on a menu of three short groups, each entry with its emblem and what it holds', async () => {
    mockApi(signedIn());
    renderAt();
    await screen.findByText('[اسم القارئ]');
    const [, hub] = screen.getAllByRole('navigation', { name: 'أقسام ملفي' });
    const groups = within(hub as HTMLElement).getAllByRole('region');
    expect(groups.map((group) => group.getAttribute('aria-label'))).toEqual([
      'أنت',
      'تجربتك',
      'خصوصيتك',
    ]);
    const data = within(hub as HTMLElement).getByRole('link', { name: /بياناتك/ });
    expect(data).toHaveTextContent('نزّل بياناتك، وسجل موافقاتك، وحذف الحساب.');
    // The emblem is decoration: the entry's name is its words.
    expect(data.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    // Nothing is open yet: no way back to show.
    expect(screen.queryByRole('button', { name: 'كل أقسام ملفي' })).toBeNull();
  });

  it('describes the account entry as an invitation for a guest', async () => {
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    renderAt();
    await screen.findByRole('link', { name: 'ادخل' });
    const [, hub] = screen.getAllByRole('navigation', { name: 'أقسام ملفي' });
    expect(within(hub as HTMLElement).getByRole('link', { name: /حسابك/ })).toHaveTextContent(
      'ادخل لتحفظ مسارك وبصائرك على أي جهاز.'
    );
  });

  it('opens one section at a time, gives it the focus, and goes back to the whole menu', async () => {
    mockApi(signedIn());
    renderAt();
    await screen.findByText('[اسم القارئ]');
    go('data');
    const data = section('بياناتك');
    expect(data).toHaveFocus();
    expect(screen.queryByRole('region', { name: 'حسابك' })).toBeNull();
    // The menu beside it marks it as the page shown.
    const [side] = screen.getAllByRole('navigation', { name: 'أقسام ملفي' });
    expect(within(side as HTMLElement).getByRole('link', { name: 'بياناتك' })).toHaveAttribute(
      'aria-current',
      'page'
    );

    // Every entry opens its own section.
    go('identity');
    expect(screen.getAllByRole('region').some((region) => region.id === 'identity')).toBe(true);
    go('app');
    expect(section('التطبيق')).toHaveFocus();

    await userEvent.click(screen.getByRole('button', { name: 'كل أقسام ملفي' }));
    expect(window.location.hash).toBe('');
    expect(window.location.href.endsWith('#')).toBe(false);
    expect(screen.queryByRole('button', { name: 'كل أقسام ملفي' })).toBeNull();
  });

  it("follows the browser's back button, and opens nothing for an address it does not know", async () => {
    mockApi(signedIn());
    renderAt('nothing-here');
    await screen.findByText('[اسم القارئ]');
    expect(screen.queryByRole('button', { name: 'كل أقسام ملفي' })).toBeNull();
    // From tablet up the first section shows beside the menu.
    expect(section('حسابك')).toBeInTheDocument();

    go('cookies');
    expect(section('ملفات تعريف الارتباط')).toBeInTheDocument();
    act(() => {
      window.history.pushState(null, '', '/me');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(screen.queryByRole('button', { name: 'كل أقسام ملفي' })).toBeNull();
  });
});
