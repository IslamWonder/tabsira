import { failureMessage } from '@/lib/api/failure-message';
import type { Failure } from '@/lib/api/result';
import { messages } from '@/messages';

const SCAN_ERRORS: Readonly<Record<string, string>> = messages.scan.errors;

/**
 * The words for a scan that did not start or did not finish, by the API's own
 * stable code (v2 §26): what happened, and what to do next. A code with no
 * sentence of its own falls to the general messages, which say it is a fault
 * on our side.
 */
export function codeMessage(code: string): string | undefined {
  return SCAN_ERRORS[code];
}

/** The sentence for a failed call of the journey. */
export function journeyFailureMessage(failure: Failure): string {
  return codeMessage(failure.code) ?? failureMessage(failure);
}

/** The sentence for a scan whose run ended `failed` with `code`. */
export function failedRunMessage(code: string | null): string {
  return (code === null ? undefined : codeMessage(code)) ?? messages.errors.server;
}
