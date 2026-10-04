import { describe, expect, it } from 'vitest';
import { featureCameraDiscovery, featureFlag } from './server-env';

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

  it('name the camera discovery flag', () => {
    expect(featureCameraDiscovery({ FEATURE_CAMERA_DISCOVERY: 'false' })).toBe(false);
    expect(featureCameraDiscovery({ FEATURE_CAMERA_DISCOVERY: 'true' })).toBe(true);
    expect(featureCameraDiscovery()).toBe(true);
  });
});
