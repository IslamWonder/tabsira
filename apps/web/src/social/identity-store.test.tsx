import { act, render, screen, waitFor } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { setGuest, setSignedIn } from '@/account/session';
import { apiError, mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { IDENTITY, NO_IDENTITY } from '@/test/social';
import {
  forgetIdentity,
  hasIdentity,
  loadIdentity,
  setIdentity,
  useIdentity,
} from './identity-store';

function Probe() {
  const identity = useIdentity();
  return <p>{identity.status}</p>;
}

describe('the identity store', () => {
  it('asks the API once a person is signed in and shares the answer', async () => {
    const api = mockApi({ 'GET /me/public-identity': { body: IDENTITY } });
    setSignedIn(USER);
    render(
      <>
        <Probe />
        <Probe />
      </>
    );
    await waitFor(() => expect(screen.getAllByText('ready')).toHaveLength(2));
    expect(api.requests).toHaveLength(1);
  });

  it('is unavailable when the API cannot answer, and unknown for a guest', async () => {
    mockApi({ 'GET /me/public-identity': apiError(500, 'INTERNAL') });
    setSignedIn(USER);
    render(<Probe />);
    await waitFor(() => expect(screen.getByText('unavailable')).toBeInTheDocument());
    act(() => setGuest());
    render(<Probe />);
    // Both readers: the guest, and the one who just signed out.
    expect(screen.getAllByText('unknown')).toHaveLength(2);
  });

  it('forgets the identity when the person signs out', async () => {
    mockApi({ 'GET /me/public-identity': { body: IDENTITY } });
    setSignedIn(USER);
    const { rerender } = render(<Probe />);
    await waitFor(() => expect(screen.getByText('ready')).toBeInTheDocument());
    act(() => setGuest());
    rerender(<Probe />);
    expect(screen.getByText('unknown')).toBeInTheDocument();
    // Signing in again asks again: the store was reset, not just hidden.
    const api = mockApi({ 'GET /me/public-identity': { body: IDENTITY } });
    act(() => setSignedIn(USER));
    rerender(<Probe />);
    await waitFor(() => expect(screen.getByText('ready')).toBeInTheDocument());
    expect(api.requests).toHaveLength(1);
  });

  it('drops an answer that arrives after a reset', async () => {
    let answer: (() => void) | null = null;
    mockApi({
      'GET /me/public-identity': () =>
        new Promise((resolve) => {
          answer = () => resolve({ body: IDENTITY });
        }),
    });
    const pending = loadIdentity();
    await waitFor(() => expect(answer).not.toBeNull());
    forgetIdentity();
    (answer as unknown as () => void)();
    await pending;
    setSignedIn(USER);
    const api = mockApi({ 'GET /me/public-identity': { body: NO_IDENTITY } });
    render(<Probe />);
    await waitFor(() => expect(screen.getByText('ready')).toBeInTheDocument());
    expect(api.requests).toHaveLength(1);
  });

  it('is unknown on the server', () => {
    setSignedIn(USER);
    expect(renderToString(<Probe />)).toContain('unknown');
  });

  it('knows when both the handle and the public name are chosen', () => {
    expect(hasIdentity({ status: 'unknown' })).toBe(false);
    expect(hasIdentity({ status: 'ready', identity: NO_IDENTITY })).toBe(false);
    setIdentity(IDENTITY);
    expect(hasIdentity({ status: 'ready', identity: IDENTITY })).toBe(true);
  });
});
