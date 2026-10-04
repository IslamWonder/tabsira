import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { POLICY, RECORD } from '@/test/fixtures';

const jar = vi.hoisted(() => ({ values: new Map<string, string>() }));
vi.mock('next/headers', () => ({
  cookies: async () => ({
    get: (name: string) => (jar.values.has(name) ? { value: jar.values.get(name) } : undefined),
  }),
}));

const { serverConsent } = await import('./server');

beforeEach(() => {
  jar.values.clear();
});

describe('the cookie choice seen by the server', () => {
  it('opens the screen on a first visit, with the policy', async () => {
    const api = mockApi({ 'GET /consent/policy': { body: POLICY } });
    expect(await serverConsent()).toEqual({
      consent: { status: 'asking', reason: 'first' },
      policy: POLICY,
      view: 'summary',
      failed: false,
    });
    expect(api.requests[0]?.url).toBe('http://127.0.0.1:8000/consent/policy');
  });

  it('keeps it closed for a choice the API confirms, with one call', async () => {
    jar.values.set('tabsira_consent', RECORD.consent_id);
    const api = mockApi({ [`GET /consent/${RECORD.consent_id}`]: { body: RECORD } });
    expect(await serverConsent()).toMatchObject({
      consent: { status: 'decided', record: RECORD },
      policy: null,
    });
    expect(api.requests).toHaveLength(1);
  });

  it('asks again when the API says the choice lapsed, naming why', async () => {
    jar.values.set('tabsira_consent', RECORD.consent_id);
    mockApi({
      [`GET /consent/${RECORD.consent_id}`]: { body: { ...RECORD, reask: true } },
      'GET /consent/policy': { body: { ...POLICY, policy_version: '2027-01-01' } },
    });
    expect((await serverConsent()).consent).toEqual({ status: 'asking', reason: 'version' });
    mockApi({
      [`GET /consent/${RECORD.consent_id}`]: { body: { ...RECORD, reask: true } },
      'GET /consent/policy': { body: POLICY },
    });
    expect((await serverConsent()).consent).toEqual({ status: 'asking', reason: 'time' });
  });

  it('asks afresh for an id the API never issued', async () => {
    jar.values.set('tabsira_consent', RECORD.consent_id);
    mockApi({
      [`GET /consent/${RECORD.consent_id}`]: apiError(404, 'NOT_FOUND'),
      'GET /consent/policy': 'network-error',
    });
    expect(await serverConsent()).toMatchObject({
      consent: { status: 'asking', reason: 'first' },
      policy: null,
    });
  });

  it('stays closed and grants nothing when the API cannot answer', async () => {
    jar.values.set('tabsira_consent', RECORD.consent_id);
    mockApi({ [`GET /consent/${RECORD.consent_id}`]: 'network-error' });
    expect((await serverConsent()).consent).toEqual({ status: 'unavailable' });
  });

  it('respects a refusal the API could not record, and the view a form asked for', async () => {
    jar.values.set('tabsira_consent_dismissed', '1');
    jar.values.set('tabsira_consent_view', 'failed');
    mockApi({});
    expect(await serverConsent()).toEqual({
      consent: { status: 'dismissed' },
      policy: null,
      view: 'summary',
      failed: true,
    });
    jar.values.clear();
    jar.values.set('tabsira_consent_view', 'customise');
    mockApi({ 'GET /consent/policy': { body: POLICY } });
    expect(await serverConsent()).toMatchObject({ view: 'customise', failed: false });
  });
});
