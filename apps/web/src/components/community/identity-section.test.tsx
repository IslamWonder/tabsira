import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi, type Route } from '@/test/api';
import { USER } from '@/test/fixtures';
import { IDENTITY, NO_IDENTITY, OTHER } from '@/test/social';
import { IdentitySection } from './identity-section';

vi.mock('next/navigation', () => ({ usePathname: () => '/me' }));

function member(extra: Record<string, Route> = {}, identity: object = IDENTITY, user = USER) {
  return mockApi({
    'GET /auth/me': { body: user },
    'GET /me/public-identity': { body: identity },
    'GET /blocks': { body: [] },
    ...extra,
  });
}

describe('IdentitySection', () => {
  it('is not there for a guest', async () => {
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    const { container } = render(<IdentitySection />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('asks an unverified account to verify first', async () => {
    member({}, NO_IDENTITY, { ...USER, email_verified: false });
    render(<IdentitySection />);
    expect(await screen.findByText(/أكّد بريدك أولًا لتختار هوية عامة/)).toBeInTheDocument();
    expect(screen.queryByLabelText('المعرّف')).toBeNull();
  });

  it('checks the handle and the name before sending, then saves and links the public page', async () => {
    const api = member(
      { 'PUT /me/public-identity': { body: { handle: 'rain_reader', public_name: 'قارئ المطر' } } },
      NO_IDENTITY
    );
    render(<IdentitySection />);
    expect(await screen.findByText(/لم تختر هوية عامة بعد/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('المعرّف'), 'admin');
    await userEvent.click(screen.getByRole('button', { name: 'احفظ هويتي' }));
    expect(screen.getByLabelText('المعرّف')).toHaveAccessibleDescription(/محجوز للمنصة/);
    expect(screen.getByLabelText('الاسم العام')).toHaveAccessibleDescription(/اكتب اسمًا عامًا/);
    expect(api.requests.filter((r) => r.method === 'PUT')).toHaveLength(0);

    await userEvent.clear(screen.getByLabelText('المعرّف'));
    await userEvent.type(screen.getByLabelText('المعرّف'), 'rain_reader');
    await userEvent.type(screen.getByLabelText('الاسم العام'), 'قارئ  المطر');
    await userEvent.click(screen.getByRole('button', { name: 'احفظ هويتي' }));
    expect(await screen.findByText('حُفظ اختيارك.')).toBeInTheDocument();
    expect(await api.bodies('PUT', '/me/public-identity')).toEqual([
      { handle: 'rain_reader', public_name: 'قارئ المطر' },
    ]);
    expect(screen.getByRole('link', { name: 'صفحتك العامة' })).toHaveAttribute(
      'href',
      '/u/rain_reader'
    );
  });

  it('says when the handle is taken', async () => {
    member({ 'PUT /me/public-identity': apiError(409, 'HANDLE_TAKEN') }, NO_IDENTITY);
    render(<IdentitySection />);
    await userEvent.type(await screen.findByLabelText('المعرّف'), 'reader');
    await userEvent.type(screen.getByLabelText('الاسم العام'), 'قارئ');
    await userEvent.click(screen.getByRole('button', { name: 'احفظ هويتي' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/يحمله عضو آخر/);
    expect(screen.getByLabelText('المعرّف')).toBeInvalid();
  });

  it('lists the blocked members and lifts a block', async () => {
    member({ 'GET /blocks': { body: [OTHER] }, 'DELETE /blocks/other_one': { status: 204 } });
    render(<IdentitySection />);
    expect(await screen.findByText('[عضو آخر]')).toBeInTheDocument();
    expect(screen.getByLabelText('المعرّف')).toHaveValue('reader');
    await userEvent.click(screen.getByRole('button', { name: 'ألغِ الحجب' }));
    await waitFor(() => expect(screen.queryByText('[عضو آخر]')).toBeNull());
    expect(screen.getByText('ألغيت الحجب.')).toBeInTheDocument();
    expect(screen.getByText('لم تحجب أحدًا.')).toBeInTheDocument();
  });
});
