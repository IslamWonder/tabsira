'use client';

import { useEffect, useMemo, useSyncExternalStore } from 'react';
import { fetchPolicy, fetchRecord, postConsent } from './api';
import {
  type ConsentChoices,
  type ConsentPolicy,
  type ConsentRecord,
  type ConsentRequest,
  OPTIONAL_CATEGORIES,
  type OptionalCategory,
} from './contract';
import {
  clearConsentId,
  readConsentId,
  readDismissed,
  writeConsentId,
  writeDismissed,
} from './cookie';

/*
 * The visitor's cookie choice (owner decision 32), as a store every part of
 * the page can read: the consent screen, the profile page (/me), and `<ConsentGate>`, which
 * the analytics tools will sit behind. Nothing is granted until the API has
 * recorded or confirmed a choice; until then every optional category is off.
 */

export type AskReason = 'first' | 'version' | 'time';

export type ConsentStatus =
  /** The server render, and the first client render. */
  | { status: 'unknown' }
  /** A stored consent id is being confirmed with the API. */
  | { status: 'checking' }
  /** No valid choice: the screen asks (first visit, a new policy version, or after reask_days). */
  | { status: 'asking'; reason: AskReason }
  | { status: 'decided'; record: ConsentRecord }
  /** A stored choice could not be confirmed: nothing is granted, and nothing is forced on the visitor. */
  | { status: 'unavailable' }
  /** Rejected while the API could not record it: nothing granted, not asked again this session. */
  | { status: 'dismissed' };

export type PolicyLoad =
  | { status: 'idle' | 'loading' | 'failed' }
  | { status: 'ready'; policy: ConsentPolicy };

export interface ConsentSnapshot {
  consent: ConsentStatus;
  policy: PolicyLoad;
  /** The visitor reopened the screen from the footer or the profile page. */
  settingsOpen: boolean;
}

const INITIAL: ConsentSnapshot = {
  consent: { status: 'unknown' },
  policy: { status: 'idle' },
  settingsOpen: false,
};

let snapshot: ConsentSnapshot = INITIAL;
let policyRequest: Promise<ConsentPolicy | null> | null = null;
const listeners = new Set<() => void>();

function update(patch: Partial<ConsentSnapshot>): void {
  snapshot = { ...snapshot, ...patch };
  for (const listener of listeners) {
    listener();
  }
}

export function readConsent(): ConsentSnapshot {
  return snapshot;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The policy (version, re-ask delay, categories), asked once; a failure can be retried. */
export function loadPolicy(): Promise<ConsentPolicy | null> {
  if (snapshot.policy.status === 'ready') {
    return Promise.resolve(snapshot.policy.policy);
  }
  if (policyRequest === null) {
    update({ policy: { status: 'loading' } });
    policyRequest = fetchPolicy().then((answer) => {
      policyRequest = null;
      update({
        policy: answer.ok ? { status: 'ready', policy: answer.data } : { status: 'failed' },
      });
      return answer.ok ? answer.data : null;
    });
  }
  return policyRequest;
}

/**
 * Whether the recorded choice still holds, or why it must be asked again. The
 * API says when it lapsed (`reask`: a new policy version, or reask_days
 * passed); the policy, when known, tells which of the two.
 */
export function staleReason(record: ConsentRecord, policy: ConsentPolicy | null): AskReason | null {
  if (!record.reask) {
    return null;
  }
  return policy !== null && policy.policy_version !== record.policy_version ? 'version' : 'time';
}

/** Tells Google's Consent Mode, when its defaults script is on the page (GA configured). */
function syncConsentMode(choices: ConsentChoices | null): void {
  const gtag = (window as { gtag?: (...args: unknown[]) => void }).gtag;
  if (typeof gtag === 'function') {
    gtag('consent', 'update', {
      analytics_storage: choices?.analytics === true ? 'granted' : 'denied',
    });
  }
}

async function confirmStored(id: string): Promise<void> {
  const [policy, answer] = await Promise.all([loadPolicy(), fetchRecord(id)]);
  if (!answer.ok) {
    if (answer.reason === 'not-found') {
      clearConsentId();
      update({ consent: { status: 'asking', reason: 'first' } });
    } else {
      update({ consent: { status: 'unavailable' } });
    }
    return;
  }
  const reason = staleReason(answer.data, policy);
  if (reason === null) {
    update({ consent: { status: 'decided', record: answer.data } });
    syncConsentMode(answer.data.categories);
  } else {
    update({ consent: { status: 'asking', reason } });
  }
}

/** Looks at the stored choice once per page load; the screen opens at once on a first visit. */
export function initConsent(): void {
  if (snapshot.consent.status !== 'unknown') {
    return;
  }
  const id = readConsentId();
  if (id !== null) {
    update({ consent: { status: 'checking' } });
    void confirmStored(id);
    return;
  }
  if (readDismissed()) {
    update({ consent: { status: 'dismissed' } });
    return;
  }
  update({ consent: { status: 'asking', reason: 'first' } });
  void loadPolicy();
}

/** The visitor's earlier anonymous id goes along, so the API keeps one record per visitor. */
function requestFor(policy: ConsentPolicy, choices: ConsentChoices): ConsentRequest {
  const previous = readConsentId();
  return {
    ...(previous === null ? {} : { consent_id: previous }),
    policy_version: policy.policy_version,
    ...choices,
  };
}

function rejectsAll(choices: ConsentChoices): boolean {
  return OPTIONAL_CATEGORIES.every((category) => !choices[category]);
}

/**
 * Records a choice with the API, then keeps its id in the cookie. Returns
 * whether it was recorded. Rejecting always closes the screen: when the API
 * cannot record it, nothing is granted for this visit and the old cookie goes,
 * so a refusal is never undone by an earlier yes.
 */
export async function decide(choices: ConsentChoices): Promise<boolean> {
  const policy = await loadPolicy();
  const answer = policy === null ? null : await postConsent(requestFor(policy, choices));
  if (policy !== null && answer?.ok === true) {
    writeConsentId(answer.data.consent_id);
    writeDismissed(false);
    update({ consent: { status: 'decided', record: answer.data }, settingsOpen: false });
    syncConsentMode(answer.data.categories);
    return true;
  }
  if (rejectsAll(choices)) {
    clearConsentId();
    writeDismissed(true);
    update({ consent: { status: 'dismissed' }, settingsOpen: false });
    syncConsentMode(null);
  }
  return false;
}

/** The footer link and the profile page: show the screen again, with the current choice. */
export function openConsentSettings(): void {
  void loadPolicy();
  update({ settingsOpen: true });
}

export function closeConsentSettings(): void {
  update({ settingsOpen: false });
}

/**
 * What the web server found when it rendered the page (src/consent/server.ts):
 * the screen is in the HTML already when it must ask, so the page starts
 * from the same answer and never asks the API again for it.
 */
export interface ServerConsent {
  consent: Exclude<ConsentStatus, { status: 'unknown' } | { status: 'checking' }>;
  policy: ConsentPolicy | null;
  /** For a visitor without JavaScript: the view the form asked for, or its failed save. */
  view: 'summary' | 'customise';
  failed: boolean;
}

export function snapshotOf(server: ServerConsent): ConsentSnapshot {
  // The server asks the policy only when the screen asks; then a missing one failed.
  const missing: PolicyLoad =
    server.consent.status === 'asking' ? { status: 'failed' } : { status: 'idle' };
  return {
    consent: server.consent,
    policy: server.policy === null ? missing : { status: 'ready', policy: server.policy },
    settingsOpen: false,
  };
}

/** Starts the page's store from the server's answer, once, before anything else reads it. */
function seed(server: ConsentSnapshot): void {
  if (snapshot.consent.status === 'unknown') {
    snapshot = server;
  }
}

/**
 * The store for the parts the server rendered with the screen's state (the
 * screen itself and the page under it): the first client render matches the
 * server's HTML exactly, so nothing flashes or shifts when the page hydrates.
 */
export function useSeededConsent(server: ServerConsent): ConsentSnapshot {
  const initial = useMemo(() => snapshotOf(server), [server]);
  if (typeof window !== 'undefined') {
    seed(initial);
  }
  return useSyncExternalStore(subscribe, readConsent, () => initial);
}

/** Forgets everything, as at a fresh page load (between unit tests). */
export function forgetConsent(): void {
  policyRequest = null;
  snapshot = INITIAL;
}

function serverSnapshot(): ConsentSnapshot {
  return INITIAL;
}

export function useConsent(): ConsentSnapshot {
  const current = useSyncExternalStore(subscribe, readConsent, serverSnapshot);
  useEffect(() => {
    initConsent();
  }, []);
  return current;
}

/** Whether `category` is allowed now: only after the API recorded or confirmed a yes. */
export function isGranted(state: ConsentStatus, category: OptionalCategory): boolean {
  return state.status === 'decided' && state.record.categories[category];
}
