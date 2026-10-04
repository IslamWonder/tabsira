import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { createApiClient } from './client';
import { isLegalRefusal, onLegalRequired } from './legal-signal';

describe('the global legal refusal', () => {
  it('is reported by every API client, and leaves the answer readable', async () => {
    const heard = vi.fn();
    const stop = onLegalRequired(heard);
    mockApi({ 'GET /profile': apiError(403, 'legal_acceptance_required') });
    const result = await createApiClient().GET('/profile');
    expect(heard).toHaveBeenCalledOnce();
    expect(result.error).toMatchObject({ error: 'legal_acceptance_required' });
    stop();
    await createApiClient().GET('/profile');
    expect(heard).toHaveBeenCalledOnce();
  });

  it('is only that 403', async () => {
    expect(await isLegalRefusal(new Response('{}', { status: 401 }))).toBe(false);
    expect(await isLegalRefusal(new Response('{"error":"FORBIDDEN"}', { status: 403 }))).toBe(
      false
    );
    expect(await isLegalRefusal(new Response('<html>', { status: 403 }))).toBe(false);
    expect(
      await isLegalRefusal(new Response('{"error":"LEGAL_ACCEPTANCE_REQUIRED"}', { status: 403 }))
    ).toBe(true);
  });
});
