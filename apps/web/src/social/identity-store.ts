'use client';

import { useEffect, useSyncExternalStore } from 'react';
import { useSession } from '@/account/session';
import { getIdentity } from './api';
import type { PublicIdentity } from './types';

/*
 * The signed-in person's public handle and name, asked once per page load and
 * shared by every screen that needs to know whether they may post or comment
 * (the API answers 409 PUBLIC_IDENTITY_REQUIRED until both are chosen).
 */

export type IdentityState =
  | { status: 'unknown' }
  | { status: 'loading' }
  | { status: 'ready'; identity: PublicIdentity }
  | { status: 'unavailable' };

const UNKNOWN: IdentityState = { status: 'unknown' };
let state: IdentityState = UNKNOWN;
let pending: Promise<void> | null = null;
const listeners = new Set<() => void>();

function publish(next: IdentityState): void {
  state = next;
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function loadIdentity(): Promise<void> {
  pending ??= getIdentity().then((result) => {
    pending = null;
    publish(result.ok ? { status: 'ready', identity: result.data } : { status: 'unavailable' });
  });
  publish({ status: 'loading' });
  return pending;
}

/** After the identity is saved: what the API returned. */
export function setIdentity(identity: PublicIdentity): void {
  publish({ status: 'ready', identity });
}

/** As at a fresh page load (between unit tests, and after signing out). */
export function forgetIdentity(): void {
  pending = null;
  state = UNKNOWN;
}

/** Who the signed-in person is on the network; `unknown` for a guest and until asked. */
export function useIdentity(): IdentityState {
  const session = useSession();
  const current = useSyncExternalStore(
    subscribe,
    () => state,
    () => UNKNOWN
  );
  const signedIn = session.status === 'signed-in';
  useEffect(() => {
    if (signedIn && state.status === 'unknown') {
      void loadIdentity();
    }
    if (!signedIn && state.status !== 'unknown') {
      forgetIdentity();
      publish(UNKNOWN);
    }
  }, [signedIn]);
  return signedIn ? current : UNKNOWN;
}

/** Whether the person has chosen both a handle and a public name. */
export function hasIdentity(state: IdentityState): state is {
  status: 'ready';
  identity: { handle: string; public_name: string };
} {
  return (
    state.status === 'ready' &&
    state.identity.handle !== null &&
    state.identity.public_name !== null
  );
}
