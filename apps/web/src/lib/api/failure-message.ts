import { messages } from '@/messages';
import type { Failure, FailureCode } from './result';

const E = messages.errors;

const BY_CODE: Partial<Record<FailureCode, string>> = {
  NETWORK: E.network,
  UNAUTHORIZED: E.unauthorized,
  ORIGIN_NOT_ALLOWED: E.origin,
  INVALID_CREDENTIALS: E.invalidCredentials,
  ACCOUNT_DISABLED: E.accountDisabled,
  EMAIL_TAKEN: E.emailTaken,
  INVALID_TOKEN: E.invalidToken,
  EMAIL_NOT_VERIFIED: E.emailNotVerified,
  CONSENT_NOT_ALLOWED: E.consentNotAllowed,
  GOOGLE_NOT_CONFIGURED: E.googleNotConfigured,
  VALIDATION_ERROR: E.validation,
  LEGAL_ACCEPTANCE_REQUIRED: E.legalStale,
};

/**
 * The sentence a reader sees for a failed request: what happened and what to
 * do next (tajriba §3.5). A code without a sentence of its own is a fault on
 * our side, said as such.
 */
export function failureMessage(failure: Failure): string {
  if (failure.code === 'LEGAL_ACCEPTANCE_REQUIRED' && failure.status === 403) {
    // Not an error of the screen: the acceptance gate opens over it.
    return E.legalRequired;
  }
  if (failure.code === 'RATE_LIMITED') {
    return failure.retryAfter === null
      ? E.rateLimitedSoon
      : E.rateLimited(E.minutes(Math.ceil(failure.retryAfter / 60)));
  }
  return BY_CODE[failure.code] ?? E.server;
}
