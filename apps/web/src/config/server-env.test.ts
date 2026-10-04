import { describe, expect, it, vi } from 'vitest';
import {
  adminInspectorUrl,
  featureAtlas,
  featureCameraDiscovery,
  featureFlag,
  featureSocial,
  turnstileSiteKey,
} from './server-env';

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

describe('the feature flags the web server reads', () => {
  it('are on unless the environment file says otherwise, read as the API reads them', () => {
    expect(featureFlag('ATLAS', {})).toBe(true);
    expect(featureFlag('ATLAS', { FEATURE_ATLAS: '' })).toBe(true);
    for (const yes of ['true', 'True', ' 1 ', 'yes', 'on', 'y', 't']) {
      expect(featureFlag('ATLAS', { FEATURE_ATLAS: yes })).toBe(true);
    }
    for (const no of ['false', 'False', '0', 'no', 'off', 'nonsense']) {
      expect(featureFlag('ATLAS', { FEATURE_ATLAS: no })).toBe(false);
    }
  });

  it('name the atlas and the network flags', () => {
    expect(featureAtlas({ FEATURE_ATLAS: 'false' })).toBe(false);
    expect(featureAtlas({ FEATURE_ATLAS: 'true' })).toBe(true);
    expect(featureAtlas()).toBe(true);
    expect(featureSocial({ FEATURE_SOCIAL: 'false' })).toBe(false);
    expect(featureSocial({ FEATURE_SOCIAL: 'true' })).toBe(true);
    expect(featureSocial()).toBe(true);
  });

  it('name the camera discovery flag', () => {
    expect(featureCameraDiscovery({ FEATURE_CAMERA_DISCOVERY: 'false' })).toBe(false);
    expect(featureCameraDiscovery({ FEATURE_CAMERA_DISCOVERY: 'true' })).toBe(true);
    expect(featureCameraDiscovery()).toBe(true);
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
