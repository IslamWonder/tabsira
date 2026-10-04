import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { POLICY, RECORD } from '@/test/fixtures';
import { fetchPolicy, fetchRecord, postConsent } from './api';

describe('the consent calls', () => {
  it('reads the policy and records a choice through the typed client', async () => {
    const api = mockApi({
      'GET /consent/policy': { body: POLICY },
      'POST /consent': { status: 201, body: RECORD },
    });
    expect(await fetchPolicy()).toEqual({ ok: true, data: POLICY });
    expect(api.requests[0]?.url).toBe('https://api.tabsira.test/consent/policy');
    expect(
      await postConsent({
        policy_version: '2026-10-04',
        necessary: true,
        analytics: false,
        behaviour: false,
      })
    ).toEqual({ ok: true, data: RECORD });
  });

  it('names an unknown id (never issued, or not an id at all) apart from a failure', async () => {
    mockApi({ 'GET /consent/x%2Fy': apiError(404, 'NOT_FOUND') });
    expect(await fetchRecord('x/y')).toEqual({ ok: false, reason: 'not-found' });
    mockApi({ 'GET /consent/abc': apiError(422, 'VALIDATION_ERROR') });
    expect(await fetchRecord('abc')).toEqual({ ok: false, reason: 'not-found' });
    mockApi({ 'GET /consent/policy': apiError(500, 'INTERNAL_ERROR') });
    expect(await fetchPolicy()).toEqual({ ok: false, reason: 'failed' });
    mockApi({ 'GET /consent/policy': 'network-error' });
    expect(await fetchPolicy()).toEqual({ ok: false, reason: 'failed' });
  });
});
