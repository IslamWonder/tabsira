import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import {
  loadSession,
  markTutorialClosed,
  readSession,
  setGuest,
  setSignedIn,
  signOut,
  tutorialOffered,
  useSession,
} from './session';

function Probe() {
  const session = useSession();
  return <p>{session.status}</p>;
}

describe('the session store', () => {
  it('stops offering the example once the account holds an insight of its own', () => {
    expect(tutorialOffered(readSession())).toBe(true);
    markTutorialClosed();
    expect(readSession()).toEqual({ status: 'unknown' });
    setGuest();
    expect(tutorialOffered(readSession())).toBe(true);
    setSignedIn(USER);
    expect(tutorialOffered(readSession())).toBe(true);

    markTutorialClosed();

    expect(tutorialOffered(readSession())).toBe(false);
    const closed = readSession();
    markTutorialClosed();
    expect(readSession()).toBe(closed);
  });

  it('asks the API once, however many readers, and knows the account', async () => {
    const api = mockApi({ 'GET /auth/me': { body: USER } });
    render(
      <>
        <Probe />
        <Probe />
      </>
    );
    expect(screen.getAllByText('unknown')).toHaveLength(2);
    await waitFor(() => expect(screen.getAllByText('signed-in')).toHaveLength(2));
    expect(api.requests).toHaveLength(1);
    expect(readSession()).toEqual({ status: 'signed-in', user: USER });
  });

  it('is a guest on 401 and unavailable when the API cannot answer', async () => {
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    expect(await loadSession()).toEqual({ status: 'guest' });
    mockApi({ 'GET /auth/me': 'network-error' });
    expect(await loadSession()).toEqual({ status: 'unavailable' });
  });

  it('does not ask again once it knows', async () => {
    const api = mockApi({ 'GET /auth/me': { body: USER } });
    setGuest();
    render(<Probe />);
    expect(screen.getByText('guest')).toBeInTheDocument();
    expect(api.requests).toHaveLength(0);
  });

  it('signs out on the server, then becomes a guest', async () => {
    mockApi({ 'POST /auth/logout': { status: 204 } });
    let told = false;
    expect(await signOut(() => (told = true))).toBeNull();
    expect(told).toBe(true);
    expect(readSession()).toEqual({ status: 'guest' });
    mockApi({ 'POST /auth/logout': apiError(403, 'ORIGIN_NOT_ALLOWED') });
    expect(await signOut()).toMatchObject({ code: 'ORIGIN_NOT_ALLOWED' });
  });
});
