import { loadProfile, type Profile, patchProfile } from '@/account/profile';
import { readSession } from '@/account/session';
import { setThemePreference, type ThemePreference } from '@/theme/theme';
import { setAmbientMotion } from './motion';

/**
 * Theme and motion follow the account across devices. The device's own value
 * (localStorage, applied by the inline script) shows first, so nothing
 * flashes; once the profile is loaded the account's value replaces it. A guest
 * never reaches the API, and signing out leaves the last value on the device.
 */

type ReducedMotion = Profile['reduced_motion'];

/** The account says «reduce motion» as `on`; `system` and `off` leave the device in charge. */
export function ambientFromAccount(reducedMotion: ReducedMotion): boolean {
  return reducedMotion !== 'on';
}

export function accountFromAmbient(ambient: boolean): ReducedMotion {
  return ambient ? 'system' : 'on';
}

/** Makes the device show what the account keeps. */
export function applyAccountPreferences(profile: Pick<Profile, 'theme' | 'reduced_motion'>): void {
  setThemePreference(profile.theme);
  setAmbientMotion(ambientFromAccount(profile.reduced_motion));
}

/** Loads the signed-in person's profile and applies it; a failure leaves the device's choice. */
export async function syncFromAccount(): Promise<void> {
  const result = await loadProfile();
  if (result.ok) {
    applyAccountPreferences(result.data);
  }
}

/**
 * Keeps a change made on this device in the account too, when signed in. The
 * change already shows; if the API refuses it, the device keeps it until the
 * next sign-in, which takes the account's value.
 */
async function remember(patch: { theme: ThemePreference } | { reduced_motion: ReducedMotion }) {
  if (readSession().status === 'signed-in') {
    await patchProfile(patch);
  }
}

export function rememberTheme(theme: ThemePreference): Promise<void> {
  return remember({ theme });
}

export function rememberAmbientMotion(ambient: boolean): Promise<void> {
  return remember({ reduced_motion: accountFromAmbient(ambient) });
}
