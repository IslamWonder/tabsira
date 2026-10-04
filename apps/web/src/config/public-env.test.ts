import { describe, expect, it } from 'vitest';
import {
  DEVELOPMENT_API_URL,
  DEVELOPMENT_SITE_URL,
  mergeEnv,
  PublicEnvError,
  resolveEnvironment,
  resolveOrigin,
  resolveProfileQuestionsMax,
  resolvePublicEnv,
} from './public-env';

describe('resolvePublicEnv', () => {
  it('uses the .test addresses in development when nothing is set', () => {
    expect(resolvePublicEnv({})).toEqual({
      environment: 'development',
      siteUrl: DEVELOPMENT_SITE_URL,
      apiUrl: DEVELOPMENT_API_URL,
      profileQuestionsMax: 3,
    });
  });

  it('prefers NEXT_PUBLIC_* over the shared SITE_URL and API_URL', () => {
    const env = resolvePublicEnv({
      ENVIRONMENT: 'production',
      SITE_URL: 'https://shared.example',
      API_URL: 'https://api.shared.example',
      NEXT_PUBLIC_SITE_URL: 'https://tabsira.me',
      NEXT_PUBLIC_API_URL: 'https://api.tabsira.me/',
    });
    expect(env).toEqual({
      environment: 'production',
      siteUrl: 'https://tabsira.me',
      apiUrl: 'https://api.tabsira.me',
      profileQuestionsMax: 3,
    });
  });

  it('reads PROFILE_QUESTIONS_MAX from the shared .env, NEXT_PUBLIC_ first, and bounds it', () => {
    expect(resolvePublicEnv({ PROFILE_QUESTIONS_MAX: '2' }).profileQuestionsMax).toBe(2);
    expect(
      resolvePublicEnv({ PROFILE_QUESTIONS_MAX: '2', NEXT_PUBLIC_PROFILE_QUESTIONS_MAX: '0' })
        .profileQuestionsMax
    ).toBe(0);
    expect(resolveProfileQuestionsMax(' 1 ')).toBe(1);
    expect(resolveProfileQuestionsMax(undefined)).toBe(3);
    for (const bad of ['4', '-1', '1.5', 'three']) {
      expect(() => resolveProfileQuestionsMax(bad)).toThrow(PublicEnvError);
    }
  });

  it('falls back to the shared SITE_URL and API_URL', () => {
    const env = resolvePublicEnv({
      ENVIRONMENT: 'production',
      SITE_URL: 'https://tabsira.me',
      API_URL: 'https://api.tabsira.me',
      NEXT_PUBLIC_SITE_URL: '',
    });
    expect(env.siteUrl).toBe('https://tabsira.me');
    expect(env.apiUrl).toBe('https://api.tabsira.me');
  });

  it.each([
    'https://tabsira.test',
    'https://api.tabsira.test',
    'https://localhost:3000',
    'https://app.localhost',
    'https://127.0.0.1',
    'https://[::1]',
    'https://test',
  ])('fails a production build that points at %s', (url) => {
    expect(() =>
      resolvePublicEnv({
        ENVIRONMENT: 'production',
        NEXT_PUBLIC_SITE_URL: url,
        NEXT_PUBLIC_API_URL: 'https://api.tabsira.me',
      })
    ).toThrow(/development host/);
  });

  it('requires both addresses in production', () => {
    expect(() => resolvePublicEnv({ ENVIRONMENT: 'production' })).toThrow(
      'NEXT_PUBLIC_SITE_URL is required for a production build.'
    );
  });

  it('allows .test outside production', () => {
    expect(resolvePublicEnv({ ENVIRONMENT: 'test' }).siteUrl).toBe(DEVELOPMENT_SITE_URL);
  });
});

describe('resolveOrigin', () => {
  it.each([
    ['not a url', /is not a URL/],
    ['ftp://tabsira.me', /must use https/],
    ['https://tabsira.me/path', /must be an origin/],
    ['https://tabsira.me/?q=1', /must be an origin/],
    ['https://tabsira.me/#x', /must be an origin/],
    ['https://user@tabsira.me', /must be an origin/],
  ])('refuses %s', (value, message) => {
    expect(() => resolveOrigin('X', value, '', 'development')).toThrow(message);
  });

  it('refuses plain http in production only', () => {
    expect(resolveOrigin('X', 'http://tabsira.me', '', 'development')).toBe('http://tabsira.me');
    expect(() => resolveOrigin('X', 'http://tabsira.me', '', 'production')).toThrow(
      /https in production/
    );
  });

  it('trims the value and keeps a port', () => {
    expect(resolveOrigin('X', '  https://tabsira.me:8443  ', '', 'production')).toBe(
      'https://tabsira.me:8443'
    );
  });

  it('raises a named error type', () => {
    expect(() => resolveOrigin('X', '', '', 'production')).toThrow(PublicEnvError);
  });
});

describe('resolveEnvironment', () => {
  it('defaults to development and accepts the three names', () => {
    expect(resolveEnvironment(undefined)).toBe('development');
    expect(resolveEnvironment('')).toBe('development');
    expect(resolveEnvironment('test')).toBe('test');
    expect(resolveEnvironment('production')).toBe('production');
  });

  it('refuses anything else', () => {
    expect(() => resolveEnvironment('prod')).toThrow('ENVIRONMENT must be');
  });
});

describe('mergeEnv', () => {
  it('lets the process environment win over the file, for the keys it reads only', () => {
    const merged = mergeEnv(
      { SITE_URL: 'https://file.example', API_URL: 'https://api.file.example', SECRET: 'x' },
      { SITE_URL: 'https://process.example', ENVIRONMENT: 'production' }
    );
    expect(merged).toEqual({
      ENVIRONMENT: 'production',
      SITE_URL: 'https://process.example',
      API_URL: 'https://api.file.example',
      NEXT_PUBLIC_SITE_URL: undefined,
      NEXT_PUBLIC_API_URL: undefined,
      PROFILE_QUESTIONS_MAX: undefined,
      NEXT_PUBLIC_PROFILE_QUESTIONS_MAX: undefined,
    });
  });
});
