// @vitest-environment node
import { ImageResponse } from 'next/og';
import { afterEach, describe, expect, it } from 'vitest';
import { CARD_HEIGHT, CARD_WIDTH, shareCard } from '@/components/public-insight/share-card';
import { cardFonts, coveredCodePoints } from '@/lib/share-card-fonts';
import { publicInsightOut } from '@/test/scan';

/*
 * The one test that draws real pixels: the renderer must accept the fonts and
 * every string of the card, and must never reach for a font elsewhere (any
 * fetch fails loudly here).
 */

const realFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = realFetch;
});

describe('drawing the share card', () => {
  it('renders a PNG from the real fonts without any network request, in under a second once warm', async () => {
    const fetches: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      // The renderer loads its own WebAssembly from a data: URL; nothing else may be fetched.
      if (url.startsWith('data:')) {
        return realFetch(input, init);
      }
      fetches.push(url);
      throw new Error('no network in a unit test');
    }) as typeof fetch;
    const [fonts, covered] = await Promise.all([cardFonts(), coveredCodePoints()]);
    const insights = [
      publicInsightOut(),
      publicInsightOut({
        label: 'مثال موثّق مُعدّ',
        author: { public_name: 'Firas 😀 中文' },
        title: 'عنوان طويل للبصيرة يمتد على سطرين كاملين في البطاقة حتى نرى ما يحدث للنص الطويل',
      }),
    ];
    let warm = Number.POSITIVE_INFINITY;
    for (const [index, insight] of insights.entries()) {
      const started = performance.now();
      const png = await new ImageResponse(
        shareCard(insight, new URL('https://tabsira.me'), covered),
        { width: CARD_WIDTH, height: CARD_HEIGHT, fonts }
      ).arrayBuffer();
      const elapsed = performance.now() - started;
      const bytes = new Uint8Array(png);
      expect(Array.from(bytes.subarray(1, 4), (b) => String.fromCharCode(b)).join('')).toBe('PNG');
      expect(bytes.byteLength).toBeGreaterThan(10_000);
      if (index > 0) {
        warm = Math.min(warm, elapsed);
      }
    }
    expect(fetches).toEqual([]);
    expect(warm).toBeLessThan(1000);
  }, 60_000);
});
