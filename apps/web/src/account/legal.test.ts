import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { LEGAL } from '@/test/legal';
import { acceptanceOf, acceptLegal, fetchLegal, loadLegal } from './legal';

describe('the legal texts', () => {
  it('reads the current versions once, with the session cookie', async () => {
    const api = mockApi({ 'GET /legal': { body: LEGAL } });
    expect(await loadLegal()).toMatchObject({ ok: true, data: LEGAL });
    expect(await loadLegal()).toMatchObject({ ok: true });
    expect(api.requests).toHaveLength(1);
    expect(api.requests[0]?.credentials).toBe('include');
    expect(acceptanceOf(LEGAL)).toEqual({
      accepted_terms_version: '2026-10-04',
      accepted_privacy_version: '2026-10-04',
    });
  });

  it('refuses an answer of the wrong shape and passes errors on', async () => {
    mockApi({ 'GET /legal': { body: { ...LEGAL, terms_version: '' } } });
    expect(await fetchLegal()).toMatchObject({ ok: false, code: 'INTERNAL_ERROR' });
    mockApi({ 'GET /legal': { body: null } });
    expect(await fetchLegal()).toMatchObject({ ok: false });
    mockApi({ 'GET /legal': apiError(503, 'SERVICE_UNAVAILABLE') });
    expect(await loadLegal()).toMatchObject({ ok: false, code: 'SERVICE_UNAVAILABLE' });
    mockApi({ 'GET /legal': { status: 502, body: undefined } });
    expect(await loadLegal()).toMatchObject({ ok: false, code: 'INTERNAL_ERROR' });
  });

  it('records an acceptance of exactly the versions read', async () => {
    const api = mockApi({ 'POST /auth/legal/accept': { status: 204 } });
    expect(await acceptLegal(LEGAL)).toMatchObject({ ok: true });
    expect(await api.bodies('POST', '/auth/legal/accept')).toEqual([
      { terms_version: '2026-10-04', privacy_version: '2026-10-04' },
    ]);
    mockApi({ 'POST /auth/legal/accept': apiError(422, 'legal_acceptance_required') });
    expect(await acceptLegal(LEGAL)).toMatchObject({
      ok: false,
      code: 'LEGAL_ACCEPTANCE_REQUIRED',
    });
  });
});
