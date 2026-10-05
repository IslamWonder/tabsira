import { describe, expect, it } from 'vitest';
import {
  DEFAULT_LANDING,
  fragmentToken,
  googleStartUrl,
  safeNextPath,
  signUpReason,
} from './links';

describe('safeNextPath', () => {
  it('keeps a path inside the app', () => {
    expect(safeNextPath('/world?x=1')).toBe('/world?x=1');
    expect(safeNextPath(['/atlas', '/me'])).toBe('/atlas');
  });

  it('drops anything that could leave the app', () => {
    for (const value of [
      undefined,
      null,
      '',
      'https://evil.example',
      '//evil.example',
      '/\\evil.example',
      '/a\nb',
      '/a\u007fb',
      `/${'a'.repeat(600)}`,
    ]) {
      expect(safeNextPath(value)).toBe(DEFAULT_LANDING);
    }
  });
});

describe('fragmentToken', () => {
  it('reads #token= and refuses what cannot be a token', () => {
    const token = 'a'.repeat(43);
    expect(fragmentToken(`#token=${token}`)).toBe(token);
    expect(fragmentToken('#token=short')).toBeNull();
    expect(fragmentToken('')).toBeNull();
    expect(fragmentToken(`#token=${'a'.repeat(300)}`)).toBeNull();
  });
});

describe('googleStartUrl', () => {
  it('starts the sign-in at the API with where to land', () => {
    expect(googleStartUrl('/me')).toBe('https://api.tabsira.test/auth/google/start?next=%2Fme');
  });
});

describe('signUpReason', () => {
  it('keeps the two reasons a guest is sent to sign up and drops the rest', () => {
    expect(signUpReason('scan')).toBe('scan');
    expect(signUpReason(['chat', 'scan'])).toBe('chat');
    expect(signUpReason('<b>')).toBeUndefined();
    expect(signUpReason(undefined)).toBeUndefined();
  });
});
