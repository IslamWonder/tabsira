import { cookies } from 'next/headers';
import { cache } from 'react';
import type { ConsentPolicy } from './contract';
import { CONSENT_COOKIE, DISMISSED_COOKIE, VIEW_COOKIE, validConsentId, validView } from './cookie';
import { policyOnServer, recordOnServer } from './server-api';
import type { ServerConsent } from './store';

async function policyOrNull(): Promise<ConsentPolicy | null> {
  const result = await policyOnServer();
  return result.ok ? result.data : null;
}

/**
 * The cookie choice as the web server sees it, once per request (owner
 * decision 32 and the owners' "no flash" review): no valid choice means the
 * screen is open from the first byte of HTML. A stored id is checked with
 * GET /consent/{id}; the API says when it lapsed (a new policy version, or
 * its re-ask delay). An API that cannot answer leaves the screen closed and
 * grants nothing, as the page itself would.
 */
export const serverConsent = cache(async (): Promise<ServerConsent> => {
  const jar = await cookies();
  const view = validView(jar.get(VIEW_COOKIE)?.value);
  const shown = {
    view: view === 'customise' ? ('customise' as const) : ('summary' as const),
    failed: view === 'failed',
  };
  const id = validConsentId(jar.get(CONSENT_COOKIE)?.value);

  if (id === null) {
    if (jar.get(DISMISSED_COOKIE)?.value === '1') {
      return { consent: { status: 'dismissed' }, policy: null, ...shown };
    }
    return {
      consent: { status: 'asking', reason: 'first' },
      policy: await policyOrNull(),
      ...shown,
    };
  }

  const record = await recordOnServer(id);
  if (record.ok && !record.data.reask) {
    // The common case, a returning visitor: one call, and the policy only if they reopen the screen.
    return { consent: { status: 'decided', record: record.data }, policy: null, ...shown };
  }
  if (!record.ok && record.code !== 'NOT_FOUND' && record.code !== 'VALIDATION_ERROR') {
    return { consent: { status: 'unavailable' }, policy: null, ...shown };
  }
  const policy = await policyOrNull();
  const changed =
    record.ok && policy !== null && policy.policy_version !== record.data.policy_version;
  const later = changed ? 'version' : 'time';
  const reason = record.ok ? later : 'first';
  return { consent: { status: 'asking', reason }, policy, ...shown };
});
