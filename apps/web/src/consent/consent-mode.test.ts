// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import { consentModeDefaults } from '@/components/consent/consent-mode-defaults';
import { clarityProjectId, gaMeasurementId } from '@/config/server-env';
import { CONSENT_MODE_DEFAULTS } from './consent-mode';

vi.mock('next/server', () => ({ connection: async () => undefined }));

describe('the analytics configuration', () => {
  it('reads GA_MEASUREMENT_ID and refuses what is not a measurement id', () => {
    expect(gaMeasurementId({ GA_MEASUREMENT_ID: ' G-AB12CD34 ' })).toBe('G-AB12CD34');
    expect(gaMeasurementId({ GA_MEASUREMENT_ID: '' })).toBeNull();
    expect(gaMeasurementId({})).toBeNull();
    expect(gaMeasurementId({ GA_MEASUREMENT_ID: 'G-1";alert(1)' })).toBeNull();
  });
});

describe('the heatmap configuration', () => {
  it('reads CLARITY_PROJECT_ID and refuses what is not a project id', () => {
    expect(clarityProjectId({ CLARITY_PROJECT_ID: ' k3x9abcd12 ' })).toBe('k3x9abcd12');
    expect(clarityProjectId({ CLARITY_PROJECT_ID: '' })).toBeNull();
    expect(clarityProjectId({})).toBeNull();
    expect(clarityProjectId({ CLARITY_PROJECT_ID: 'x";alert(1)' })).toBeNull();
    vi.stubEnv('CLARITY_PROJECT_ID', 'k3x9abcd12');
    expect(clarityProjectId()).toBe('k3x9abcd12');
  });
});

describe('the Consent Mode defaults', () => {
  it('deny everything, load nothing and send nothing', () => {
    for (const key of ['ad_storage', 'ad_user_data', 'ad_personalization', 'analytics_storage']) {
      expect(CONSENT_MODE_DEFAULTS).toContain(`${key}:'denied'`);
    }
    expect(CONSENT_MODE_DEFAULTS).not.toMatch(/https?:|src=|config/);
  });

  it('are rendered only when GA is configured, as read at request time', async () => {
    vi.stubEnv('GA_MEASUREMENT_ID', '');
    expect(await consentModeDefaults()).toBeNull();
    vi.stubEnv('GA_MEASUREMENT_ID', 'G-AB12CD34');
    const script = await consentModeDefaults();
    expect(script?.props).toMatchObject({
      id: 'consent-mode-defaults',
      dangerouslySetInnerHTML: { __html: CONSENT_MODE_DEFAULTS },
    });
  });
});

describe('the server address of the API', () => {
  it('prefers API_INTERNAL_URL, then the development API on loopback, then the public address', async () => {
    const { serverApiOrigin } = await import('@/config/server-env');
    expect(serverApiOrigin({ API_INTERNAL_URL: ' http://127.0.0.1:8000/ignored ' })).toBe(
      'http://127.0.0.1:8000'
    );
    expect(serverApiOrigin({ API_INTERNAL_URL: '', NODE_ENV: 'production' })).toBe(
      'https://api.tabsira.test'
    );
    expect(serverApiOrigin({ NODE_ENV: 'development' })).toBe('http://127.0.0.1:8000');
  });
});
