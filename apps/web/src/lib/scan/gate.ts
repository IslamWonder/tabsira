import type { Route } from 'next';
import type { Failure } from '@/lib/api/result';

/*
 * Decision 63: a guest gets the rain tutorial and one scan of their own; then the server answers
 * 403 `account_required`, and the way on is sign-up, with the way back kept in `next`.
 */

export type SignUpReason = 'scan' | 'chat';

/** The sign-up page, back to `returnTo` afterwards, with the line that says why it was asked. */
export function signUpHref(returnTo: string, reason?: SignUpReason): Route {
  const query = new URLSearchParams({ next: returnTo });
  if (reason !== undefined) {
    query.set('reason', reason);
  }
  return `/signup?${query.toString()}` as Route;
}

/** The refusal of a second scan by a guest. */
export function accountRequired(failure: Failure): boolean {
  return failure.status === 403 && failure.code === 'ACCOUNT_REQUIRED';
}

/** The refusal of a scan or a chat message by an account whose profile is not complete. */
export function profileRequired(failure: Failure): boolean {
  return failure.status === 403 && failure.code === 'PROFILE_REQUIRED';
}
