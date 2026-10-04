import { beforeEach, describe, expect, it, vi } from 'vitest';
import { forgetSession, setGuest, setSignedIn } from '@/account/session';
import { PROFILE, USER } from '@/test/fixtures';
import {
  accountFromAmbient,
  ambientFromAccount,
  rememberAmbientMotion,
  rememberTheme,
  syncFromAccount,
} from './account-sync';

const loadProfile = vi.hoisted(() => vi.fn());
const patchProfile = vi.hoisted(() => vi.fn());
vi.mock('@/account/profile', () => ({ loadProfile, patchProfile }));

beforeEach(() => {
  forgetSession();
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.removeAttribute('data-motion');
  vi.clearAllMocks();
});

describe('account preferences', () => {
  it('maps the account motion value to the device switch and back', () => {
    expect(ambientFromAccount('on')).toBe(false);
    expect(ambientFromAccount('off')).toBe(true);
    expect(ambientFromAccount('system')).toBe(true);
    expect(accountFromAmbient(false)).toBe('on');
    expect(accountFromAmbient(true)).toBe('system');
  });

  it('lets the account win over the device after sign-in', async () => {
    window.localStorage.setItem('tabsira.theme', 'light');
    loadProfile.mockResolvedValue({
      ok: true,
      data: { ...PROFILE, theme: 'dark', reduced_motion: 'on' },
    });
    await syncFromAccount();
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.dataset.motion).toBe('reduce');
  });

  it('keeps the device choice when the profile cannot be loaded', async () => {
    window.localStorage.setItem('tabsira.theme', 'light');
    loadProfile.mockResolvedValue({ ok: false });
    await syncFromAccount();
    expect(window.localStorage.getItem('tabsira.theme')).toBe('light');
  });

  it('saves a change to the account only when signed in', async () => {
    patchProfile.mockResolvedValue({ ok: true });
    setGuest();
    await rememberTheme('dark');
    expect(patchProfile).not.toHaveBeenCalled();
    setSignedIn(USER);
    await rememberTheme('dark');
    await rememberAmbientMotion(false);
    expect(patchProfile).toHaveBeenNthCalledWith(1, { theme: 'dark' });
    expect(patchProfile).toHaveBeenNthCalledWith(2, { reduced_motion: 'on' });
  });
});
