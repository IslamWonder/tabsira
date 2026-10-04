import { describe, expect, it } from 'vitest';
import { PLACE_ONE, PLACE_TWO, RELATION, WORLD, WORLD_UNDER_FOG } from '@/test/world';
import { insightHref, openedCount, regionState, regionViews, threads } from './world-model';

describe('regionViews', () => {
  it('joins each opened region to its place and flags a ready treasure', () => {
    const views = regionViews(WORLD);
    expect(views.map((view) => view.place?.id ?? null)).toEqual(['7001', '7002', null, null]);
    expect(views.map((view) => view.hasTreasure)).toEqual([false, true, false, false]);
    expect(openedCount(views)).toBe(2);
  });

  it('keeps a whole map under fog for a newcomer', () => {
    const views = regionViews(WORLD_UNDER_FOG);
    expect(openedCount(views)).toBe(0);
  });

  it('treats a place the API did not send as still under fog', () => {
    const views = regionViews({ ...WORLD, places: [PLACE_ONE] });
    expect(views[1]?.place).toBeNull();
  });
});

describe('regionState', () => {
  it('says each state in words, one source for the map and the list', () => {
    const views = regionViews(WORLD);
    expect(regionState(views[3] as (typeof views)[number])).toBe('تحت الضباب');
    expect(regionState(views[0] as (typeof views)[number])).toBe('بصيرة واحدة محفوظة');
    expect(regionState(views[1] as (typeof views)[number])).toBe('2 بصائر محفوظة، فيها كنز ينتظر');
    const empty = regionViews({ ...WORLD, places: [{ ...PLACE_ONE, insights: [] }, PLACE_TWO] });
    expect(regionState(empty[0] as (typeof views)[number])).toBe('مفتوحة');
  });
});

describe('threads', () => {
  it('keeps a relation whose two places are both on the map', () => {
    const views = regionViews(WORLD);
    const found = threads(views, WORLD.relations);
    expect(found).toHaveLength(1);
    expect(found[0]?.from.region.id).toBe('T00');
    expect(found[0]?.to.region.id).toBe('T01');
  });

  it('leaves out a relation to a place that is not shown', () => {
    const views = regionViews({ ...WORLD, places: [PLACE_ONE] });
    expect(threads(views, [RELATION])).toEqual([]);
    expect(threads(views, [{ ...RELATION, place_a_id: '1', place_b_id: '2' }])).toEqual([]);
  });
});

describe('insightHref', () => {
  it('leads to the insight screen by the insight id', () => {
    expect(insightHref('9001')).toBe('/insight/9001');
  });
});
