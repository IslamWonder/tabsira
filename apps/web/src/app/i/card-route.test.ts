// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { publicInsightOut } from '@/test/scan';
import { forgetDrawnCards, GET } from './[id]/card.png/route';

const rendered = vi.fn();

vi.mock('next/og', () => ({
  // A constructor function that hands back a Response, as the real ImageResponse does.
  ImageResponse: function ImageResponse(
    element: unknown,
    options: { fonts: unknown[]; width: number; height: number }
  ) {
    rendered(element, options);
    return new Response('png', { status: 200 });
  },
}));

const ID = '110000000000000002';
const params = (id: string) => ({ params: Promise.resolve({ id }) });
const request = () => new Request('https://tabsira.test');

afterEach(() => {
  forgetDrawnCards();
  rendered.mockClear();
  vi.restoreAllMocks();
});

describe('the share card route', () => {
  it('draws the published insight once with the card fonts, then serves the drawn card for five minutes', async () => {
    const api = mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    const response = await GET(request(), params(ID));
    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toBe('image/png');
    expect(response.headers.get('cache-control')).toBe('public, max-age=300');
    expect(await response.text()).toBe('png');
    const [, options] = rendered.mock.calls[0] as [unknown, { fonts: { name: string }[] }];
    expect(options.fonts).toHaveLength(4);
    expect(options).toMatchObject({ width: 1200, height: 630 });

    const again = await GET(request(), params(ID));
    expect(again.status).toBe(200);
    expect(rendered).toHaveBeenCalledTimes(1);
    // The API is still asked each time: a withdrawn insight stops at once.
    expect(api.requests).toHaveLength(2);
  });

  it('draws a card again once five minutes have passed', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    const start = Date.now();
    const now = vi.spyOn(Date, 'now').mockReturnValue(start);
    await GET(request(), params(ID));
    now.mockReturnValue(start + 301_000);
    await GET(request(), params(ID));
    expect(rendered).toHaveBeenCalledTimes(2);
  });

  it('answers 404 for a bad id without asking the API, and for an insight that is not public', async () => {
    const api = mockApi({ [`GET /public/insights/${ID}`]: apiError(404, 'NOT_FOUND') });
    expect((await GET(request(), params('abc'))).status).toBe(404);
    expect(api.requests).toHaveLength(0);
    expect((await GET(request(), params(ID))).status).toBe(404);
    expect(rendered).not.toHaveBeenCalled();
  });

  it('forgets the oldest card when a hundred are kept', async () => {
    const ids = Array.from({ length: 101 }, (_, i) => (110000000000000100n + BigInt(i)).toString());
    mockApi(
      Object.fromEntries(
        ids.map((id) => [`GET /public/insights/${id}`, { body: publicInsightOut({ id }) }])
      )
    );
    for (const id of ids) {
      expect((await GET(request(), params(id))).status).toBe(200);
    }
    expect(rendered).toHaveBeenCalledTimes(101);
    // The first card was forgotten and is drawn again, which forgets the second; the third is kept.
    await GET(request(), params(ids[0] as string));
    expect(rendered).toHaveBeenCalledTimes(102);
    await GET(request(), params(ids[2] as string));
    expect(rendered).toHaveBeenCalledTimes(102);
  });
});
