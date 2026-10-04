// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { publicInsightOut } from '@/test/share';
import { GET } from './route';

const ID = '110000000000000002';

function get(id: string) {
  return GET(new Request(`https://tabsira.test/insights/${id}/card`), {
    params: Promise.resolve({ id }),
  });
}

describe('GET /insights/{id}/card', () => {
  it('answers a PNG that no cache keeps, so a withdrawal shows at once', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    const response = await get(ID);
    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toBe('image/png');
    expect(response.headers.get('Cache-Control')).toBe('no-store');
    const bytes = Buffer.from(await response.arrayBuffer());
    expect(bytes.subarray(1, 4).toString()).toBe('PNG');
  });

  it('answers 404 for anything that is not public, with nothing cached', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: apiError(404, 'NOT_FOUND') });
    for (const id of [ID, 'abc']) {
      const response = await get(id);
      expect(response.status).toBe(404);
      expect(response.headers.get('Cache-Control')).toBe('no-store');
      expect(await response.text()).toBe('');
    }
  });

  it('answers 503 when the API does not answer, so a crawler tries again', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: 'network-error' });
    const response = await get(ID);
    expect(response.status).toBe(503);
    expect(response.headers.get('Cache-Control')).toBe('no-store');
  });
});
