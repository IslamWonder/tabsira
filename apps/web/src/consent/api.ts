import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { ConsentPolicy, ConsentRecord, ConsentRequest } from './contract';

/** What a consent request came to: the answer, a record the API does not know, or a failure. */
export type Answer<T> = { ok: true; data: T } | { ok: false; reason: 'not-found' | 'failed' };

function answer<T>(result: Result<T>): Answer<T> {
  if (result.ok) {
    return { ok: true, data: result.data };
  }
  // An id the API never issued (404), or one that is not even an id (422).
  const unknown = result.code === 'NOT_FOUND' || result.code === 'VALIDATION_ERROR';
  return { ok: false, reason: unknown ? 'not-found' : 'failed' };
}

export async function fetchPolicy(): Promise<Answer<ConsentPolicy>> {
  return answer(await attempt(api.GET('/consent/policy')));
}

export async function fetchRecord(consentId: string): Promise<Answer<ConsentRecord>> {
  return answer(
    await attempt(api.GET('/consent/{consent_id}', { params: { path: { consent_id: consentId } } }))
  );
}

/**
 * Records a choice. The session cookie rides along like on every call: a
 * signed-in visitor's choices are exported and deleted with the account.
 */
export async function postConsent(body: ConsentRequest): Promise<Answer<ConsentRecord>> {
  return answer(await attempt(api.POST('/consent', { body })));
}
