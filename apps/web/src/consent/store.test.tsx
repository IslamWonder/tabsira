import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { POLICY, RECORD } from '@/test/fixtures';
import { ConsentGate } from './consent-gate';
import { ACCEPT_ALL, REJECT_ALL } from './contract';
import { readConsentId, readDismissed, writeConsentId, writeDismissed } from './cookie';
import {
  closeConsentSettings,
  decide,
  initConsent,
  isGranted,
  loadPolicy,
  openConsentSettings,
  readConsent,
  type ServerConsent,
  snapshotOf,
  staleReason,
  useSeededConsent,
} from './store';

async function settled() {
  await waitFor(() => expect(readConsent().consent.status).not.toBe('checking'));
}

describe('the consent store on a first visit', () => {
  it('asks at once and loads the policy', async () => {
    mockApi({ 'GET /consent/policy': { body: POLICY } });
    initConsent();
    expect(readConsent().consent).toEqual({ status: 'asking', reason: 'first' });
    await waitFor(() => expect(readConsent().policy).toEqual({ status: 'ready', policy: POLICY }));
    initConsent();
    expect(readConsent().consent.status).toBe('asking');
    expect(await loadPolicy()).toEqual(POLICY);
  });

  it('records a choice, keeps its id in the cookie and tells Consent Mode', async () => {
    const gtag = vi.fn();
    vi.stubGlobal('gtag', gtag);
    const api = mockApi({
      'GET /consent/policy': { body: POLICY },
      'POST /consent': { body: RECORD },
    });
    initConsent();
    expect(await decide(ACCEPT_ALL)).toBe(true);
    expect(readConsent().consent).toEqual({ status: 'decided', record: RECORD });
    expect(readConsentId()).toBe(RECORD.consent_id);
    expect(await api.bodies('POST', '/consent')).toEqual([
      { policy_version: POLICY.policy_version, ...ACCEPT_ALL },
    ]);
    expect(api.requests.at(-1)?.credentials).toBe('include');
    expect(gtag).toHaveBeenCalledWith('consent', 'update', { analytics_storage: 'granted' });
    expect(isGranted(readConsent().consent, 'analytics')).toBe(true);
    expect(isGranted(readConsent().consent, 'behaviour')).toBe(false);
  });

  it('sends the earlier id along when the choice is changed', async () => {
    writeConsentId('earlier-id');
    const api = mockApi({
      'GET /consent/policy': { body: POLICY },
      'POST /consent': { body: RECORD },
    });
    expect(await decide(REJECT_ALL)).toBe(true);
    expect(await api.bodies('POST', '/consent')).toEqual([
      { consent_id: 'earlier-id', policy_version: POLICY.policy_version, ...REJECT_ALL },
    ]);
  });

  it('a refusal the API cannot record still closes, grants nothing and forgets an old yes', async () => {
    writeConsentId('earlier-id');
    const gtag = vi.fn();
    vi.stubGlobal('gtag', gtag);
    mockApi({ 'GET /consent/policy': 'network-error' });
    expect(await decide(REJECT_ALL)).toBe(false);
    expect(readConsent().consent).toEqual({ status: 'dismissed' });
    expect(readConsentId()).toBeNull();
    expect(gtag).toHaveBeenCalledWith('consent', 'update', { analytics_storage: 'denied' });
    expect(readDismissed()).toBe(true);
  });

  it('a yes the API cannot record stays a question', async () => {
    mockApi({
      'GET /consent/policy': { body: POLICY },
      'POST /consent': apiError(500, 'INTERNAL_ERROR'),
    });
    initConsent();
    expect(await decide(ACCEPT_ALL)).toBe(false);
    expect(readConsent().consent.status).toBe('asking');
  });

  it('does not ask again in a session where it was dismissed', () => {
    writeDismissed(true);
    initConsent();
    expect(readConsent().consent).toEqual({ status: 'dismissed' });
  });
});

describe('the consent store with a stored id', () => {
  it('confirms a current choice with the API', async () => {
    writeConsentId(RECORD.consent_id);
    mockApi({
      'GET /consent/policy': { body: POLICY },
      [`GET /consent/${RECORD.consent_id}`]: {
        body: { ...RECORD, decided_at: new Date().toISOString() },
      },
    });
    initConsent();
    expect(readConsent().consent.status).toBe('checking');
    await settled();
    expect(readConsent().consent.status).toBe('decided');
  });

  it('asks again when the API says the choice lapsed, naming why', async () => {
    writeConsentId(RECORD.consent_id);
    mockApi({
      'GET /consent/policy': { body: { ...POLICY, policy_version: '2027-01-01' } },
      [`GET /consent/${RECORD.consent_id}`]: { body: { ...RECORD, reask: true } },
    });
    initConsent();
    await settled();
    expect(readConsent().consent).toEqual({ status: 'asking', reason: 'version' });
    expect(staleReason({ ...RECORD, reask: true }, POLICY)).toBe('time');
    expect(staleReason({ ...RECORD, reask: true }, null)).toBe('time');
    expect(staleReason(RECORD, POLICY)).toBeNull();
  });

  it('trusts the record while the policy cannot be read', async () => {
    writeConsentId(RECORD.consent_id);
    mockApi({
      'GET /consent/policy': 'network-error',
      [`GET /consent/${RECORD.consent_id}`]: { body: RECORD },
    });
    initConsent();
    await settled();
    expect(readConsent().consent.status).toBe('decided');
  });

  it('asks afresh when the API does not know the id', async () => {
    writeConsentId(RECORD.consent_id);
    mockApi({
      'GET /consent/policy': { body: POLICY },
      [`GET /consent/${RECORD.consent_id}`]: apiError(404, 'NOT_FOUND'),
    });
    initConsent();
    await settled();
    expect(readConsent().consent).toEqual({ status: 'asking', reason: 'first' });
    expect(readConsentId()).toBeNull();
  });

  it('grants nothing and asks nothing while the API is unreachable', async () => {
    writeConsentId(RECORD.consent_id);
    mockApi({
      'GET /consent/policy': { body: POLICY },
      [`GET /consent/${RECORD.consent_id}`]: apiError(503, 'SERVICE_UNAVAILABLE'),
    });
    initConsent();
    await settled();
    expect(readConsent().consent).toEqual({ status: 'unavailable' });
  });
});

describe('reopening and the gate', () => {
  it('opens and closes the settings', () => {
    mockApi({ 'GET /consent/policy': { body: POLICY } });
    openConsentSettings();
    expect(readConsent().settingsOpen).toBe(true);
    closeConsentSettings();
    expect(readConsent().settingsOpen).toBe(false);
  });

  it('shows what it guards only once the category is allowed', async () => {
    mockApi({
      'GET /consent/policy': { body: POLICY },
      'POST /consent': { body: RECORD },
    });
    render(
      <>
        <ConsentGate category="analytics">
          <p>[قياس]</p>
        </ConsentGate>
        <ConsentGate category="behaviour">
          <p>[سلوك]</p>
        </ConsentGate>
      </>
    );
    expect(screen.queryByText('[قياس]')).toBeNull();
    await decide(RECORD.categories);
    await waitFor(() => expect(screen.getByText('[قياس]')).toBeInTheDocument());
    expect(screen.queryByText('[سلوك]')).toBeNull();
  });
});

describe('the consent store started from the server', () => {
  const ASKING: ServerConsent = {
    consent: { status: 'asking', reason: 'first' },
    policy: POLICY,
    view: 'summary',
    failed: false,
  };

  function Probe({ server }: { server: ServerConsent }) {
    const { consent, policy } = useSeededConsent(server);
    return (
      <p>
        {consent.status} {policy.status}
      </p>
    );
  }

  it('starts where the server HTML is, and asks the API nothing', () => {
    const api = mockApi({});
    render(<Probe server={ASKING} />);
    expect(screen.getByText('asking ready')).toBeInTheDocument();
    initConsent();
    expect(readConsent().consent.status).toBe('asking');
    expect(api.requests).toHaveLength(0);
  });

  it('keeps what the page already learnt over a later server answer', () => {
    render(<Probe server={ASKING} />);
    const decided: ServerConsent = { ...ASKING, consent: { status: 'decided', record: RECORD } };
    render(<Probe server={decided} />);
    expect(readConsent().consent.status).toBe('asking');
  });

  it('marks a missing policy failed when asking, and not yet read otherwise', () => {
    expect(snapshotOf({ ...ASKING, policy: null }).policy).toEqual({ status: 'failed' });
    expect(
      snapshotOf({ ...ASKING, policy: null, consent: { status: 'unavailable' } }).policy
    ).toEqual({ status: 'idle' });
  });
});
