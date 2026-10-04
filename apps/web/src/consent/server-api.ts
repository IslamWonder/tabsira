import { SERVER_API_TIMEOUT_MS, serverApiOrigin } from '@/config/server-env';
import { createApiClient } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { ConsentPolicy, ConsentRecord, ConsentRequest } from './contract';

/*
 * The consent routes, called by the web server: to render the screen open in
 * the first paint, and to record a choice posted without JavaScript. A short
 * timeout: a slow API must never hold the page (AGENTS.md lessons).
 */

function client() {
  return createApiClient({ baseUrl: serverApiOrigin() });
}

const timeout = () => AbortSignal.timeout(SERVER_API_TIMEOUT_MS);

export function policyOnServer(): Promise<Result<ConsentPolicy>> {
  return attempt(client().GET('/consent/policy', { signal: timeout() }));
}

export function recordOnServer(consentId: string): Promise<Result<ConsentRecord>> {
  return attempt(
    client().GET('/consent/{consent_id}', {
      params: { path: { consent_id: consentId } },
      signal: timeout(),
    })
  );
}

/**
 * Records a choice for a visitor without JavaScript, passing on what the
 * browser would have sent itself: its user agent (the API keeps only its
 * family) and its session, so a signed-in choice stays with the account.
 */
export function postOnServer(
  body: ConsentRequest,
  visitor: { userAgent: string | null; cookies: string | null }
): Promise<Result<ConsentRecord>> {
  const headers: Record<string, string> = {};
  if (visitor.userAgent !== null) {
    headers['User-Agent'] = visitor.userAgent;
  }
  if (visitor.cookies !== null) {
    headers.Cookie = visitor.cookies;
  }
  return attempt(client().POST('/consent', { body, headers, signal: timeout() }));
}
