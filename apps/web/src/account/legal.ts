import { attempt, type Result } from '@/lib/api/result';
import { apiOrigin } from '@/lib/site';

/*
 * Accepting the terms of use and the privacy policy (owner decision 35), as
 * agreed with the API while it is being built:
 *
 *   GET  /legal              -> LegalVersions
 *   POST /auth/signup        gains accepted_terms_version and accepted_privacy_version
 *   GET  /auth/google/start  gains ?terms= and ?privacy=
 *   POST /auth/legal/accept  <- { terms_version, privacy_version }
 *   GET  /auth/me            gains legal_acceptance_required
 *
 * A missing or stale version is refused with 422 LEGAL_ACCEPTANCE_REQUIRED.
 * These shapes are not in src/lib/api/schema.d.ts yet: they are written here,
 * once, checked at runtime, and give way to the generated types when
 * `pnpm gen:api` brings them.
 */

export interface LegalVersions {
  terms_version: string;
  privacy_version: string;
  privacy_email: string;
  support_email: string;
}

export interface LegalAcceptance {
  accepted_terms_version: string;
  accepted_privacy_version: string;
}

export const LEGAL_REFUSAL = 'LEGAL_ACCEPTANCE_REQUIRED';

function isLegal(value: unknown): value is LegalVersions {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const fields = value as Record<string, unknown>;
  return ['terms_version', 'privacy_version', 'privacy_email', 'support_email'].every(
    (key) => typeof fields[key] === 'string' && fields[key] !== ''
  );
}

/** What a sign-up sends to say which texts were accepted. */
export function acceptanceOf(legal: LegalVersions): LegalAcceptance {
  return {
    accepted_terms_version: legal.terms_version,
    accepted_privacy_version: legal.privacy_version,
  };
}

/** The current versions, read through the typed client's error handling. */
export async function fetchLegal(): Promise<Result<LegalVersions>> {
  const result = await attempt(
    fetch(new URL('/legal', apiOrigin()), {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    }).then(async (response) => ({
      response,
      ...(response.ok
        ? { data: (await response.json()) as unknown }
        : { error: await errorBody(response) }),
    }))
  );
  if (result.ok && !isLegal(result.data)) {
    return {
      ok: false,
      code: 'INTERNAL_ERROR',
      status: result.status,
      fields: [],
      retryAfter: null,
    };
  }
  return result as Result<LegalVersions>;
}

async function errorBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

let cached: Promise<Result<LegalVersions>> | null = null;

/** The versions, asked once per page load; a failure is asked again next time. */
export function loadLegal(): Promise<Result<LegalVersions>> {
  cached ??= fetchLegal().then((result) => {
    if (!result.ok) {
      cached = null;
    }
    return result;
  });
  return cached;
}

/** Forgets the versions: after a refusal for a stale version, and between unit tests. */
export function forgetLegal(): void {
  cached = null;
}

/** Records the acceptance of the current texts for the signed-in account. */
export function acceptLegal(legal: LegalVersions): Promise<Result<unknown>> {
  return attempt(
    fetch(new URL('/auth/legal/accept', apiOrigin()), {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({
        terms_version: legal.terms_version,
        privacy_version: legal.privacy_version,
      }),
    }).then(async (response) => ({
      response,
      ...(response.ok ? { data: null } : { error: await errorBody(response) }),
    }))
  );
}
