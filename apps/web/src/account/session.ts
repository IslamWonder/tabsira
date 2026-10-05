'use client';

import { useEffect, useSyncExternalStore } from 'react';
import { api } from '@/lib/api/client';
import { onLegalRequired } from '@/lib/api/legal-signal';
import { attempt, type Failure } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';

/**
 * The account. `legal_acceptance_required` (owner decision 35) is not in the
 * generated schema yet; when it arrives there, this addition is redundant.
 */
export type User = components['schemas']['UserOut'] & { legal_acceptance_required?: boolean };

/**
 * Who is signed in, for this page load. The session itself is an httpOnly
 * cookie the page cannot read (docs/AUTH.md), so the answer comes from
 * `GET /auth/me`, asked once and shared by every component that needs it.
 *
 * - `unknown`: not asked yet (the server render, and the first client render).
 * - `guest`: the API answered that nobody is signed in.
 * - `signed-in`: the account, without any private profile field.
 * - `unavailable`: the API could not answer; the device settings still work.
 */
export type SessionState =
  | { status: 'unknown' }
  | { status: 'guest' }
  | { status: 'signed-in'; user: User }
  | { status: 'unavailable' };

const UNKNOWN: SessionState = { status: 'unknown' };
let state: SessionState = UNKNOWN;
let pending: Promise<SessionState> | null = null;
const listeners = new Set<() => void>();

function publish(next: SessionState): SessionState {
  state = next;
  for (const listener of listeners) {
    listener();
  }
  return next;
}

export function readSession(): SessionState {
  return state;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

// The API refused a request until the current terms are accepted: the account
// needs the acceptance gate, whatever screen met the refusal.
onLegalRequired(() => {
  if (state.status === 'signed-in' && state.user.legal_acceptance_required !== true) {
    publish({ status: 'signed-in', user: { ...state.user, legal_acceptance_required: true } });
  }
});

/** Asks the API who is signed in; one request at a time, however many callers. */
export function loadSession(): Promise<SessionState> {
  pending ??= attempt(api.GET('/auth/me')).then((result) => {
    pending = null;
    if (result.ok) {
      return publish({ status: 'signed-in', user: result.data });
    }
    return publish(
      result.code === 'UNAUTHORIZED' ? { status: 'guest' } : { status: 'unavailable' }
    );
  });
  return pending;
}

/** After a sign-in, a sign-up or a change: the account the API returned. */
export function setSignedIn(user: User): void {
  publish({ status: 'signed-in', user });
}

/**
 * The API said 403 `profile_required`: the profile form opens before anything else
 * (decision 64), whatever screen met the refusal.
 */
export function markProfileRequired(): void {
  if (state.status === 'signed-in' && state.user.profile_completed) {
    publish({ status: 'signed-in', user: { ...state.user, profile_completed: false } });
  }
}

/**
 * Decision 64 (6): an account that holds an insight of its own is no longer offered the prepared
 * rain example; its first screen is the capture. Guests and the other accounts keep it.
 */
export function tutorialOffered(session: SessionState): boolean {
  return !(session.status === 'signed-in' && session.user.has_own_insight);
}

/** The API said 403 `tutorial_closed`: the example goes, and the capture takes its place. */
export function markTutorialClosed(): void {
  if (state.status === 'signed-in' && !state.user.has_own_insight) {
    publish({ status: 'signed-in', user: { ...state.user, has_own_insight: true } });
  }
}

/** After signing out or deleting the account. */
export function setGuest(): void {
  publish({ status: 'guest' });
}

/** Ends the session on the server (its answer clears the cookie); null when it is done. */
export async function signOut(beforeGuest?: () => void): Promise<Failure | null> {
  const result = await attempt(api.POST('/auth/logout'));
  if (!result.ok) {
    return result;
  }
  beforeGuest?.();
  setGuest();
  return null;
}

/** Forgets what was learnt, as at a fresh page load (between unit tests). */
export function forgetSession(): void {
  pending = null;
  state = UNKNOWN;
}

function serverSnapshot(): SessionState {
  return UNKNOWN;
}

/** The session, asked for on first use; components re-render when it changes. */
export function useSession(): SessionState {
  const current = useSyncExternalStore(subscribe, readSession, serverSnapshot);
  useEffect(() => {
    if (readSession().status === 'unknown') {
      void loadSession();
    }
  }, []);
  return current;
}
