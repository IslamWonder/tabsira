import type { components } from '@/lib/api/schema';

/*
 * The cookie-consent API (owner decision 32), as the API publishes it:
 *
 *   GET  /consent/policy        -> ConsentPolicy
 *   POST /consent               <- ConsentRequest, -> ConsentRecord
 *   GET  /consent/{consent_id}  -> ConsentRecord, with `reask` once it lapsed
 */

export type ConsentPolicy = components['schemas']['ConsentPolicyOut'];
export type PolicyCategory = ConsentPolicy['categories'][number];
export type ConsentCategory = PolicyCategory['key'];
/** The categories a visitor chooses; the necessary one is always on. */
export type OptionalCategory = Exclude<ConsentCategory, 'necessary'>;
export type ConsentChoices = components['schemas']['ConsentCategories'];
export type ConsentRequest = components['schemas']['CookieConsentIn'];
export type ConsentRecord = components['schemas']['CookieConsentOut'];

export const OPTIONAL_CATEGORIES: readonly OptionalCategory[] = ['analytics', 'behaviour'];

export const REJECT_ALL: ConsentChoices = { necessary: true, analytics: false, behaviour: false };
export const ACCEPT_ALL: ConsentChoices = { necessary: true, analytics: true, behaviour: true };
