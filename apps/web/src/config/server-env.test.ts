import { describe, expect, it, vi } from 'vitest';
import { adminInspectorUrl, featureEnabled, landingFeatures, turnstileSiteKey } from './server-env';

describe('the Turnstile site key', () => {
  it('is read from the environment at request time, trimmed', () => {
    expect(turnstileSiteKey({ TURNSTILE_SITE_KEY: ' 0x4AAAAAAAbcdefgh ' })).toBe(
      '0x4AAAAAAAbcdefgh'
    );
  });

  it.each([
    ['unset', {}],
    ['empty', { TURNSTILE_SITE_KEY: '' }],
    ['malformed', { TURNSTILE_SITE_KEY: 'not a key!' }],
  ])('is empty, so Turnstile is off, when %s', (_name, env) => {
    expect(turnstileSiteKey(env)).toBe('');
  });

  it('reads the process environment by default', () => {
    vi.stubEnv('TURNSTILE_SITE_KEY', '1x00000000000000000000AA');
    expect(turnstileSiteKey()).toBe('1x00000000000000000000AA');
  });
});

describe('the feature switches the web server reads', () => {
  it('are on unless DISABLED_FEATURES names them, trimmed and with blanks ignored', () => {
    expect(featureEnabled('atlas', {})).toBe(true);
    expect(featureEnabled('atlas', { DISABLED_FEATURES: '' })).toBe(true);
    expect(featureEnabled('atlas', { DISABLED_FEATURES: ' chat , atlas ,,' })).toBe(false);
    expect(featureEnabled('chat', { DISABLED_FEATURES: 'atlas' })).toBe(true);
  });

  it('keep the two off-by-default features off until ENABLED_FEATURES names them', () => {
    expect(featureEnabled('social_comments', {})).toBe(false);
    expect(featureEnabled('camera_anchor', {})).toBe(false);
    expect(featureEnabled('social_comments', { ENABLED_FEATURES: 'social_comments' })).toBe(true);
    expect(featureEnabled('camera_anchor', { ENABLED_FEATURES: ' camera_anchor ' })).toBe(true);
  });

  it('give the landing page its public subset, and nothing administrative', () => {
    const features = landingFeatures({ DISABLED_FEATURES: 'chat' });
    expect(features).toEqual({
      chat: false,
      world: true,
      treasure: true,
      social: true,
      atlas: true,
      cameraDiscovery: true,
      photoStorage: true,
      canonicalVerify: true,
    });
    expect(landingFeatures().chat).toBe(true);
  });

  it('let ENABLED_FEATURES win over DISABLED_FEATURES', () => {
    const env = {
      DISABLED_FEATURES: 'chat,social_comments',
      ENABLED_FEATURES: 'chat,social_comments',
    };
    expect(featureEnabled('chat', env)).toBe(true);
    expect(featureEnabled('social_comments', env)).toBe(true);
  });

  it.each([
    ['social_comments', 'social'],
    ['atlas_sponsorship', 'atlas'],
    ['camera_anchor', 'camera_discovery'],
    ['dev_inspector', 'admin'],
  ] as const)('count %s as off while %s is off', (child, parent) => {
    expect(featureEnabled(child, { ENABLED_FEATURES: child, DISABLED_FEATURES: parent })).toBe(
      false
    );
    expect(featureEnabled(child, { ENABLED_FEATURES: child })).toBe(true);
  });

  it('ignore a name the API would refuse instead of crashing', () => {
    expect(featureEnabled('chat', { DISABLED_FEATURES: 'nonsense' })).toBe(true);
  });

  it('read the process environment by default', () => {
    vi.stubEnv('DISABLED_FEATURES', 'social');
    expect(featureEnabled('social')).toBe(false);
    expect(featureEnabled('atlas')).toBe(true);
  });
});

describe('the address of the scan inspector', () => {
  it('points at the admin area named by ADMIN_URL, under /admin/inspect', () => {
    expect(adminInspectorUrl('42', { ADMIN_URL: 'https://admin.tabsira.me' })).toBe(
      'https://admin.tabsira.me/admin/inspect/42'
    );
  });

  it('falls back to the development admin host when ADMIN_URL is unset or blank', () => {
    expect(adminInspectorUrl('42', {})).toBe('http://admin.tabsira.test/admin/inspect/42');
    expect(adminInspectorUrl('42', { ADMIN_URL: '  ' })).toBe(
      'http://admin.tabsira.test/admin/inspect/42'
    );
  });

  it('names nothing for what is not a public id', () => {
    for (const bad of ['', '0', 'abc', '-1', '1'.repeat(20), '42/..', '42?x=1']) {
      expect(adminInspectorUrl(bad, {})).toBeNull();
    }
  });
});
