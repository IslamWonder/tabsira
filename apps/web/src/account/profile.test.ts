import { describe, expect, it } from 'vitest';
import { mockApi } from '@/test/api';
import { PROFILE } from '@/test/fixtures';
import {
  CONSENT_TEXT_VERSION,
  deleteAccount,
  exportAccount,
  loadProfile,
  patchProfile,
  recordConsent,
} from './profile';

describe('the profile calls', () => {
  it('reads, patches, records a consent, exports and deletes', async () => {
    const api = mockApi({
      'GET /profile': { body: PROFILE },
      'PATCH /profile': { body: { ...PROFILE, gender: 'woman' } },
      'POST /consents': {
        status: 201,
        body: { kind: 'memory', version: CONSENT_TEXT_VERSION, granted: false, created_at: 'x' },
      },
      'GET /account/export': { body: { consents: [] } },
      'DELETE /account': { status: 204 },
    });
    expect(await loadProfile()).toMatchObject({ ok: true, data: PROFILE });
    expect(await patchProfile({ gender: 'woman' })).toMatchObject({ ok: true });
    expect(await recordConsent('memory', false)).toMatchObject({ ok: true });
    expect(await exportAccount()).toMatchObject({ ok: true });
    expect(await deleteAccount()).toMatchObject({ ok: true, status: 204 });
    expect(await api.bodies('POST', '/consents')).toEqual([
      { kind: 'memory', version: CONSENT_TEXT_VERSION, granted: false },
    ]);
    expect(api.requests.every((request) => request.credentials === 'include')).toBe(true);
  });
});
