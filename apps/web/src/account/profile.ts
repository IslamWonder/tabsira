import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';

export type Profile = components['schemas']['ProfileOut'];
export type ProfilePatch = components['schemas']['ProfilePatch'];
export type Goal = components['schemas']['Goal'];
export type KnowledgeLevel = components['schemas']['KnowledgeLevel'];
export type AgeRange = components['schemas']['AgeRange'];
export type ReligiousBackground = components['schemas']['ReligiousBackground'];
export type Gender = components['schemas']['Gender'];
export type ConsentKind = components['schemas']['ConsentKind'];
export type ConsentEntry = components['schemas']['ConsentOut'];
export type AccountExport = components['schemas']['AccountExport'];

/** The order the questions and their answers are offered in (master prompt v2 §5). */
export const GOALS: readonly Goal[] = [
  'discover_islam',
  'reflection',
  'learn_quran_sunnah',
  'live_values',
  'research',
  'teaching',
  'curiosity',
];
export const KNOWLEDGE_LEVELS: readonly KnowledgeLevel[] = [
  'new',
  'general',
  'advanced',
  'specialist',
  'unknown',
];
export const AGE_RANGES: readonly AgeRange[] = [
  'under_13',
  '13_17',
  '18_24',
  '25_39',
  '40_59',
  '60_plus',
  'unknown',
];
export const RELIGIOUS_BACKGROUNDS: readonly ReligiousBackground[] = [
  'muslim',
  'non_muslim',
  'unknown',
];
export const GENDERS: readonly Gender[] = ['man', 'woman', 'unknown'];

/**
 * The version of the consent texts the settings show (messages.settings: the
 * personalisation, memory and photo hints). It is recorded with every answer,
 * so the history says which words were agreed to: change it in the same
 * commit as those texts. 2026-10-05 added the full-name switch of the public identity.
 */
export const CONSENT_TEXT_VERSION = '2026-10-05';

/** The three switches of the profile that change only by recording a consent. */
export type ConsentSwitch = 'personalization' | 'memory' | 'photo_storage';

export const SWITCH_FIELD = {
  personalization: 'personalization_enabled',
  memory: 'memory_enabled',
  photo_storage: 'photo_storage_consent',
} as const satisfies Record<ConsentSwitch, keyof Profile>;

export function loadProfile(): Promise<Result<Profile>> {
  return attempt(api.GET('/profile'));
}

/** Changes the fields sent and no others; `unknown` clears an answer (a null is refused). */
export function patchProfile(patch: ProfilePatch): Promise<Result<Profile>> {
  return attempt(api.PATCH('/profile', { body: patch }));
}

/** Records the answer in the consent history; the profile's switch follows it. */
export function recordConsent(
  kind: ConsentSwitch,
  granted: boolean
): Promise<Result<ConsentEntry>> {
  return attempt(api.POST('/consents', { body: { kind, version: CONSENT_TEXT_VERSION, granted } }));
}

/** The separate consent to show the full name beside posts and on the public page (decision 64). */
export function recordFullNameConsent(granted: boolean): Promise<Result<ConsentEntry>> {
  return attempt(
    api.POST('/consents', {
      body: { kind: 'public_full_name', version: CONSENT_TEXT_VERSION, granted },
    })
  );
}

export function exportAccount(): Promise<Result<AccountExport>> {
  return attempt(api.GET('/account/export'));
}

export function deleteAccount(): Promise<Result<unknown>> {
  return attempt(api.DELETE('/account'));
}
