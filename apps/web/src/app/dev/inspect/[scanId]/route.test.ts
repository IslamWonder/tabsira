// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GET } from './route.dev';

function get(scanId: string) {
  return GET(new Request(`http://tabsira.test/dev/inspect/${scanId}`), {
    params: Promise.resolve({ scanId }),
  });
}

describe('GET /dev/inspect/{scanId}', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('hands over to the scan inspector of the admin area, uncached and unindexed', async () => {
    vi.stubEnv('ADMIN_URL', 'http://admin.tabsira.test');
    const response = await get('42');
    expect(response.status).toBe(307);
    expect(response.headers.get('Location')).toBe('http://admin.tabsira.test/admin/inspect/42');
    expect(response.headers.get('Cache-Control')).toBe('no-store');
    expect(response.headers.get('X-Robots-Tag')).toBe('noindex, nofollow');
    expect(await response.text()).toBe('');
  });

  it('answers 404 for what is not a scan id, and sends nothing on', async () => {
    const response = await get('abc');
    expect(response.status).toBe(404);
    expect(response.headers.get('Location')).toBeNull();
    expect(response.headers.get('X-Robots-Tag')).toBe('noindex, nofollow');
  });
});
