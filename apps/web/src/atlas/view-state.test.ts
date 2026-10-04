import { describe, expect, it } from 'vitest';
import { EMPTY_FILTERS } from './types';
import {
  atlasHref,
  EMPTY_VIEW_STATE,
  encodeViewHash,
  parseViewHash,
  zoomForRadius,
} from './view-state';

describe('the atlas view in the fragment', () => {
  it('carries the centre, zoom, selection and filters, and reads them back', () => {
    const state = {
      view: { center: [10.18153, 36.80651] as [number, number], zoom: 12.34 },
      selected: '7400000000000000001',
      filters: { period: 'month' as const, country: 'SA', concept: 'E012' },
    };
    const hash = encodeViewHash(state);
    expect(hash).toBe('#c=10.182,36.807,12.3&e=7400000000000000001&p=month&k=SA&t=E012');
    expect(parseViewHash(hash)).toEqual({
      ...state,
      view: { center: [10.182, 36.807], zoom: 12.3 },
    });
    expect(atlasHref(state)).toBe(`/atlas${hash}`);
  });

  it('carries nothing when there is nothing to carry', () => {
    expect(encodeViewHash(EMPTY_VIEW_STATE)).toBe('');
    expect(atlasHref(EMPTY_VIEW_STATE)).toBe('/atlas');
    expect(parseViewHash('')).toEqual(EMPTY_VIEW_STATE);
    expect(parseViewHash('#')).toEqual(EMPTY_VIEW_STATE);
  });

  it('drops what is malformed and clamps the zoom', () => {
    expect(parseViewHash('#c=1,2&e=abc&p=sometime&k=saudi&t=E 1')).toEqual(EMPTY_VIEW_STATE);
    expect(parseViewHash('#c=x,y,z')).toEqual(EMPTY_VIEW_STATE);
    expect(parseViewHash('#c=200,10,5')).toEqual(EMPTY_VIEW_STATE);
    expect(parseViewHash('#c=10,95,5')).toEqual(EMPTY_VIEW_STATE);
    expect(parseViewHash('#c=10,36,40').view).toEqual({ center: [10, 36], zoom: 16 });
    expect(parseViewHash('#c=10,36,0').view).toEqual({ center: [10, 36], zoom: 2 });
    expect(parseViewHash('#e=0').selected).toBeNull();
    expect(parseViewHash('#p=week').filters).toEqual({ ...EMPTY_FILTERS, period: 'week' });
  });

  it('turns a radius into a zoom that fills a phone, inside the map limits', () => {
    const near = zoomForRadius(1_500, 36.8);
    const far = zoomForRadius(20_000, 36.8);
    expect(near).toBeGreaterThan(far);
    expect(near).toBeGreaterThan(13);
    expect(near).toBeLessThan(15);
    expect(far).toBeGreaterThan(9);
    expect(far).toBeLessThan(12);
    expect(zoomForRadius(1, 0)).toBe(16);
    expect(zoomForRadius(50_000_000, 0)).toBe(2);
    // Near a pole the cosine is floored, never zero.
    expect(Number.isFinite(zoomForRadius(1_500, 90))).toBe(true);
  });
});
