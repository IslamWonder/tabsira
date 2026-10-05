import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { markProfileRequired, readSession, setSignedIn } from '@/account/session';
import { writeConsentId } from '@/consent/cookie';
import { apiError, mockApi, type Route } from '@/test/api';
import { POLICY, PROFILE, RECORD, USER } from '@/test/fixtures';
import { ProfileGate } from './profile-gate';

const pathname = vi.hoisted(() => ({ value: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => pathname.value }));

const NEW = { ...USER, profile_completed: false };

function routes(extra: Record<string, Route> = {}): Record<string, Route> {
  return {
    'GET /consent/policy': { body: POLICY },
    [`GET /consent/${RECORD.consent_id}`]: {
      body: { ...RECORD, decided_at: new Date().toISOString() },
    },
    ...extra,
  };
}

beforeEach(() => {
  pathname.value = '/';
  writeConsentId(RECORD.consent_id);
});

const submit = () => screen.getByRole('button', { name: 'احفظ وتابع' });
const preferNot = (legend: string) =>
  screen.getByRole('group', { name: legend }).querySelector('input[value="unknown"]') as Element;

async function answerEverything() {
  await userEvent.click(screen.getByRole('checkbox', { name: 'التفكر' }));
  await userEvent.click(screen.getByRole('radio', { name: 'متقدم' }));
  await userEvent.click(screen.getByRole('radio', { name: 'من 25 إلى 39' }));
  await userEvent.click(screen.getByRole('radio', { name: 'من المسلمين' }));
  await userEvent.click(screen.getByRole('radio', { name: 'أنثى' }));
}

describe('ProfileGate', () => {
  it('shows nothing for a guest, a complete profile, or the legal texts', () => {
    mockApi(routes());
    setSignedIn(USER);
    const { container, rerender } = render(<ProfileGate />);
    expect(container).toBeEmptyDOMElement();
    setSignedIn(NEW);
    pathname.value = '/terms';
    rerender(<ProfileGate />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('waits for the acceptance of the terms, which comes first', () => {
    mockApi(routes());
    setSignedIn({ ...NEW, legal_acceptance_required: true });
    render(<ProfileGate />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('asks the whole profile with nothing preselected and the button waiting for every answer', async () => {
    mockApi(routes());
    setSignedIn(NEW);
    render(<ProfileGate />);
    const dialog = await screen.findByRole('dialog', { name: 'عرّفنا بك قبل أن تبدأ' });
    expect(dialog).toHaveTextContent(/تغيّرها أو توقف التخصيص متى شئت/);
    expect(
      screen.getAllByRole('radio').filter((radio) => (radio as HTMLInputElement).checked)
    ).toHaveLength(0);
    expect(
      screen.getAllByRole('checkbox').filter((box) => (box as HTMLInputElement).checked)
    ).toHaveLength(0);
    expect(submit()).toBeDisabled();
    // «Prefer not to answer» is a choice in each of the five questions.
    expect(screen.getAllByText('أفضّل عدم الإجابة')).toHaveLength(5);
    await userEvent.click(screen.getByRole('checkbox', { name: 'التفكر' }));
    expect(submit()).toBeDisabled();
  });

  it('sends the five answers with complete_profile, then lets the person through', async () => {
    const api = mockApi(routes({ 'PATCH /profile': { body: PROFILE } }));
    setSignedIn(NEW);
    render(<ProfileGate />);
    await screen.findByRole('dialog');
    await answerEverything();
    expect(submit()).toBeEnabled();
    await userEvent.click(submit());
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await api.bodies('PATCH', '/profile')).toEqual([
      {
        goals: ['reflection'],
        knowledge_level: 'advanced',
        age_range: '25_39',
        religious_background: 'muslim',
        gender: 'woman',
        complete_profile: true,
      },
    ]);
    expect(readSession()).toMatchObject({ user: { profile_completed: true } });
  });

  it('takes «prefer not to answer» for the goals as an empty list, and for the rest as unknown', async () => {
    const api = mockApi(routes({ 'PATCH /profile': { body: PROFILE } }));
    setSignedIn(NEW);
    render(<ProfileGate />);
    await screen.findByRole('dialog');
    await userEvent.click(screen.getByRole('checkbox', { name: 'التفكر' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'أفضّل عدم الإجابة' }));
    // It excludes the goals, and a goal takes it back.
    expect(screen.getByRole('checkbox', { name: 'التفكر' })).not.toBeChecked();
    await userEvent.click(screen.getByRole('checkbox', { name: 'البحث' }));
    expect(screen.getByRole('checkbox', { name: 'أفضّل عدم الإجابة' })).not.toBeChecked();
    await userEvent.click(screen.getByRole('checkbox', { name: 'أفضّل عدم الإجابة' }));
    for (const legend of [
      'ما معرفتك السابقة بالقرآن والسنة؟',
      'فئتك العمرية',
      'خلفيتك الدينية',
      'الجنس',
    ]) {
      await userEvent.click(preferNot(legend));
    }
    await userEvent.click(submit());
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await api.bodies('PATCH', '/profile')).toEqual([
      {
        goals: [],
        knowledge_level: 'unknown',
        age_range: 'unknown',
        religious_background: 'unknown',
        gender: 'unknown',
        complete_profile: true,
      },
    ]);
  });

  it('says when the answers were not kept, and stays', async () => {
    mockApi(routes({ 'PATCH /profile': apiError(500, 'INTERNAL') }));
    setSignedIn(NEW);
    render(<ProfileGate />);
    await screen.findByRole('dialog');
    await answerEverything();
    await userEvent.click(submit());
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('opens when the API refuses a scan with profile_required, and offers to sign out', async () => {
    const api = mockApi(routes({ 'POST /auth/logout': { status: 204 } }));
    setSignedIn(USER);
    render(<ProfileGate />);
    expect(screen.queryByRole('dialog')).toBeNull();
    markProfileRequired();
    await screen.findByRole('dialog', { name: 'عرّفنا بك قبل أن تبدأ' });
    await userEvent.click(screen.getByRole('button', { name: 'اخرج من الحساب' }));
    await waitFor(() => expect(readSession().status).toBe('guest'));
    expect(api.requests.some((request) => request.url.endsWith('/auth/logout'))).toBe(true);
  });

  it('says when signing out failed', async () => {
    mockApi(routes({ 'POST /auth/logout': apiError(500, 'INTERNAL') }));
    setSignedIn(NEW);
    render(<ProfileGate />);
    await screen.findByRole('dialog');
    await userEvent.click(screen.getByRole('button', { name: 'اخرج من الحساب' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});
