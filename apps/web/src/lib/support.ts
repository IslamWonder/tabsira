import { apiOrigin } from '@/lib/site';

/*
 * Local types for POST /support and GET /auth/me. They match the API contract
 * exactly and are replaced by the generated client types (src/lib/api/schema.d.ts)
 * once the routes are in the OpenAPI document.
 */

export const SUPPORT_TOPICS = [
  'account',
  'privacy',
  'bug',
  'content',
  'suggestion',
  'other',
] as const;
export type SupportTopic = (typeof SUPPORT_TOPICS)[number];

export const MESSAGE_MIN = 20;
export const MESSAGE_MAX = 4000;

export interface SupportRequest {
  email: string;
  name?: string;
  topic: SupportTopic;
  message: string;
  /** The honeypot: people leave it empty, form-filling bots do not. */
  website: string;
}

/** What happened, in the only terms the page may tell the reader. */
export type SupportOutcome =
  | 'sent'
  | 'invalid'
  | 'rate_limited'
  | 'mail_unavailable'
  | 'turnstile_failed'
  | 'failed';

/** The 403 of a missing or bad Turnstile token carries the code `turnstile_failed` (decision 56). */
async function turnstileRefused(response: Response): Promise<boolean> {
  try {
    const body: unknown = await response.json();
    return (
      typeof body === 'object' &&
      body !== null &&
      'error' in body &&
      typeof body.error === 'string' &&
      body.error.toLowerCase() === 'turnstile_failed'
    );
  } catch {
    return false;
  }
}

/**
 * Sends the form, with the Turnstile header when there is a token. A network
 * failure and an unexpected status are `failed`, never `sent`.
 */
export async function sendSupport(
  request: SupportRequest,
  headers: Record<string, string> = {}
): Promise<SupportOutcome> {
  let response: Response;
  try {
    response = await fetch(`${apiOrigin()}/support`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify(request),
    });
  } catch {
    return 'failed';
  }
  if (response.status === 202) {
    return 'sent';
  }
  if (response.status === 403 && (await turnstileRefused(response))) {
    return 'turnstile_failed';
  }
  if (response.status === 422) {
    return 'invalid';
  }
  if (response.status === 429) {
    return 'rate_limited';
  }
  // The contract names code "mail_unavailable"; any 503 from this route means the same: nothing was sent.
  if (response.status === 503) {
    return 'mail_unavailable';
  }
  return 'failed';
}

/** The signed-in reader's address, to prefill the form; nothing when signed out or unreachable. */
export async function fetchAccountEmail(): Promise<string | undefined> {
  try {
    const response = await fetch(`${apiOrigin()}/auth/me`, { credentials: 'include' });
    if (!response.ok) {
      return undefined;
    }
    const body: unknown = await response.json();
    return typeof body === 'object' &&
      body !== null &&
      'email' in body &&
      typeof body.email === 'string'
      ? body.email
      : undefined;
  } catch {
    return undefined;
  }
}
