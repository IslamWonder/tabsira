import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readDeviceAnswers, rememberDeviceAnswer } from '@/account/device-answers';
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

  it('moves the answers a guest gave on this device into an account never asked', async () => {
    rememberDeviceAnswer({ goals: ['reflection'], age_range: '18_24' });
    loadProfile.mockResolvedValue({ ok: true, data: PROFILE });
    patchProfile.mockResolvedValue({ ok: true });
    await syncFromAccount();
    expect(patchProfile).toHaveBeenCalledWith({
      goals: ['reflection'],
      age_range: '18_24',
      questions_asked: true,
    });
    expect(readDeviceAnswers()).toBeNull();
  });

  it('keeps the device answers for the next sign-in when the account refuses them', async () => {
    rememberDeviceAnswer({ knowledge_level: 'general' });
    loadProfile.mockResolvedValue({ ok: true, data: PROFILE });
    patchProfile.mockResolvedValue({ ok: false });
    await syncFromAccount();
    expect(readDeviceAnswers()).toEqual({ knowledge_level: 'general' });
  });

  it('forgets the device answers when the account was already asked, and patches nothing', async () => {
    rememberDeviceAnswer({ knowledge_level: 'general' });
    loadProfile.mockResolvedValue({ ok: true, data: { ...PROFILE, questions_asked: true } });
    await syncFromAccount();
    expect(patchProfile).not.toHaveBeenCalled();
    expect(readDeviceAnswers()).toBeNull();
  });

  it('patches nothing at sign-in when the device holds no answers', async () => {
    loadProfile.mockResolvedValue({ ok: true, data: PROFILE });
    await syncFromAccount();
    expect(patchProfile).not.toHaveBeenCalled();
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
