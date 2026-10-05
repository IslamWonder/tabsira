import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { rememberTick } from '@/account/legal-tick';
import { readSession, setSignedIn } from '@/account/session';
import { writeConsentId } from '@/consent/cookie';
import { openConsentSettings } from '@/consent/store';
import { createApiClient } from '@/lib/api/client';
import { apiError, mockApi, type Route } from '@/test/api';
import { POLICY, RECORD, USER } from '@/test/fixtures';
import { LEGAL } from '@/test/legal';
import { LegalGate } from './legal-gate';

const pathname = vi.hoisted(() => ({ value: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => pathname.value }));

const PENDING = { ...USER, legal_acceptance_required: true };

function routes(extra: Record<string, Route> = {}): Record<string, Route> {
  return {
    'GET /consent/policy': { body: POLICY },
    [`GET /consent/${RECORD.consent_id}`]: {
      body: { ...RECORD, decided_at: new Date().toISOString() },
    },
    'GET /legal': { body: LEGAL },
    ...extra,
  };
}

beforeEach(() => {
  pathname.value = '/';
  writeConsentId(RECORD.consent_id);
});

const box = () => screen.getByRole('checkbox', { name: /أوافق على شروط الاستخدام/ });

describe('LegalGate', () => {
  it('asks a signed-in account to accept the current texts, then lets it through', async () => {
    const api = mockApi(routes({ 'POST /auth/legal/accept': { status: 200, body: {} } }));
    setSignedIn(PENDING);
    render(<LegalGate />);
    const dialog = await screen.findByRole('dialog', { name: 'قبل أن تتابع' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    const accept = screen.getByRole('button', { name: 'أوافق وأتابع' });
    await waitFor(() => expect(box()).toBeEnabled());
    expect(accept).toBeDisabled();
    await userEvent.click(box());
    await userEvent.click(accept);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await api.bodies('POST', '/auth/legal/accept')).toEqual([
      { terms_version: '2026-10-04', privacy_version: '2026-10-04' },
    ]);
    expect(readSession()).toMatchObject({ user: { legal_acceptance_required: false } });
  });

  it('offers the unticked full-name box and sends the answer only when it changes it', async () => {
    const api = mockApi(routes({ 'POST /auth/legal/accept': { status: 200, body: {} } }));
    setSignedIn(PENDING);
    render(<LegalGate />);
    const name = await screen.findByRole('checkbox', { name: /أوافق على ظهور اسمي الكامل/ });
    expect(name).not.toBeChecked();
    await waitFor(() => expect(box()).toBeEnabled());
    await userEvent.click(name);
    await userEvent.click(box());
    await userEvent.click(screen.getByRole('button', { name: 'أوافق وأتابع' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await api.bodies('POST', '/auth/legal/accept')).toEqual([
      { terms_version: '2026-10-04', privacy_version: '2026-10-04', public_full_name: true },
    ]);
    expect(readSession()).toMatchObject({ user: { public_full_name: true } });
  });

  it('reads the texts again when they changed meanwhile', async () => {
    const api = mockApi(
      routes({ 'POST /auth/legal/accept': apiError(422, 'LEGAL_ACCEPTANCE_REQUIRED') })
    );
    setSignedIn(PENDING);
    render(<LegalGate />);
    await waitFor(() => expect(box()).toBeEnabled());
    await userEvent.click(box());
    await userEvent.click(screen.getByRole('button', { name: 'أوافق وأتابع' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('تغيّرت شروط الاستخدام');
    expect(box()).not.toBeChecked();
    await waitFor(() =>
      expect(api.requests.filter((request) => request.url.endsWith('/legal'))).toHaveLength(2)
    );
  });

  it('says what went wrong when the acceptance cannot be recorded', async () => {
    mockApi(routes({ 'POST /auth/legal/accept': 'network-error' }));
    setSignedIn(PENDING);
    render(<LegalGate />);
    await waitFor(() => expect(box()).toBeEnabled());
    await userEvent.click(box());
    await userEvent.click(screen.getByRole('button', { name: 'أوافق وأتابع' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('تعذّر الوصول إلى تبصرة');
    expect(box()).toBeChecked();
  });

  it('signs out when the reader declines, and says when that fails', async () => {
    mockApi(routes({ 'POST /auth/logout': apiError(500, 'INTERNAL_ERROR') }));
    setSignedIn(PENDING);
    render(<LegalGate />);
    await userEvent.click(await screen.findByRole('button', { name: 'لا أوافق، أخرجني' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('من جهتنا');
    mockApi(routes({ 'POST /auth/logout': { status: 204 } }));
    await userEvent.click(screen.getByRole('button', { name: 'لا أوافق، أخرجني' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(readSession()).toEqual({ status: 'guest' });
  });

  it('offers to retry when the texts cannot be read', async () => {
    const api = mockApi(routes({ 'GET /legal': 'network-error' }));
    setSignedIn(PENDING);
    render(<LegalGate />);
    expect(await screen.findByText(/تعذّر تحميل نسخة الشروط/)).toBeInTheDocument();
    expect(box()).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(api.requests.filter((request) => request.url.endsWith('/legal'))).toHaveLength(2);
  });

  it('stays away from accounts that accepted, from the texts themselves and from the cookie choice', async () => {
    mockApi(routes());
    setSignedIn(USER);
    const { rerender } = render(<LegalGate />);
    expect(screen.queryByRole('dialog')).toBeNull();
    setSignedIn(PENDING);
    pathname.value = '/terms';
    rerender(<LegalGate />);
    expect(screen.queryByRole('dialog')).toBeNull();
    pathname.value = '/';
    openConsentSettings();
    rerender(<LegalGate />);
    expect(screen.queryByRole('dialog', { name: 'قبل أن تتابع' })).toBeNull();
  });

  it('says it is recording while the answer travels', async () => {
    let answer: (value: Response) => void = () => undefined;
    mockApi(
      routes({
        'POST /auth/legal/accept': () =>
          new Promise((resolve) => {
            answer = () => resolve({ status: 200, body: {} });
          }),
      })
    );
    setSignedIn(PENDING);
    render(<LegalGate />);
    await waitFor(() => expect(box()).toBeEnabled());
    await userEvent.click(box());
    await userEvent.click(screen.getByRole('button', { name: 'أوافق وأتابع' }));
    expect(screen.getByRole('button', { name: 'أسجّل موافقتك…' })).toBeDisabled();
    answer(new Response());
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});

describe('LegalGate after Google', () => {
  it('records a fresh tick for the texts in force at once, and never shows', async () => {
    const api = mockApi(routes({ 'POST /auth/legal/accept': { status: 200, body: {} } }));
    rememberTick(LEGAL, Date.now(), true);
    setSignedIn(PENDING);
    render(<LegalGate />);
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() =>
      expect(readSession()).toMatchObject({ user: { legal_acceptance_required: false } })
    );
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(await api.bodies('POST', '/auth/legal/accept')).toEqual([
      { terms_version: '2026-10-04', privacy_version: '2026-10-04', public_full_name: true },
    ]);
    expect(window.sessionStorage.getItem('tabsira.legal.tick')).toBeNull();
  });

  it('asks when the tick was for other texts', async () => {
    const api = mockApi(routes());
    rememberTick({ ...LEGAL, terms_version: '2025-01-01' });
    setSignedIn(PENDING);
    render(<LegalGate />);
    expect(await screen.findByRole('dialog', { name: 'قبل أن تتابع' })).toBeInTheDocument();
    expect(api.requests.some((request) => request.method === 'POST')).toBe(false);
  });

  it('opens when any request meets the refusal, with the texts opening in place', async () => {
    mockApi(routes({ 'GET /profile': apiError(403, 'legal_acceptance_required') }));
    setSignedIn(USER);
    render(<LegalGate />);
    expect(screen.queryByRole('dialog')).toBeNull();
    await act(async () => {
      await createApiClient().GET('/profile');
    });
    expect(await screen.findByRole('dialog', { name: 'قبل أن تتابع' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'شروط الاستخدام' })).not.toHaveAttribute('target');
  });

  it('deletes the account from the gate, after confirming in place', async () => {
    mockApi(routes({ 'DELETE /account': apiError(500, 'INTERNAL_ERROR') }));
    setSignedIn(PENDING);
    render(<LegalGate />);
    await userEvent.click(await screen.findByRole('button', { name: 'حذف الحساب' }));
    await userEvent.click(screen.getByRole('button', { name: 'تراجع' }));
    await userEvent.click(screen.getByRole('button', { name: 'حذف الحساب' }));
    await userEvent.click(screen.getByRole('button', { name: 'نعم، احذف حسابي نهائيًا' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('من جهتنا');
    mockApi(routes({ 'DELETE /account': { status: 204 } }));
    await userEvent.click(screen.getByRole('button', { name: 'نعم، احذف حسابي نهائيًا' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(readSession()).toEqual({ status: 'guest' });
  });
});
