import { describe, expect, it } from 'vitest';
import { PLACE_ONE, PLACE_TWO, REVEALS, WORLD, WORLD_JUST_LEARNED } from '@/test/world';
import type { Reveal } from '@/world/api';
import {
  announcement,
  insightHref,
  landmarkOf,
  landmarks,
  learned,
  pendingReveals,
  revealName,
  THEME_COLORS,
} from './world-model';

describe('the world model', () => {
  it('draws a landmark only where a region was first learned, named by its place', () => {
    const marks = landmarks(WORLD);

    expect(marks.map((mark) => [mark.reveal.id, mark.name])).toEqual([
      ['6001', PLACE_ONE.name],
      ['6002', PLACE_TWO.name],
    ]);
    expect(landmarkOf(WORLD, '7002')?.id).toBe('6002');
    expect(landmarkOf(WORLD, '7999')).toBeNull();
  });

  it('names a landmark by its region when its place is not in the answer', () => {
    const orphan = { ...(REVEALS[0] as Reveal), id: '6009', place_id: '7999', region_id: 'T03' };
    const world = { ...WORLD, reveals: [orphan] };

    expect(landmarks(world)[0]?.name).toBe('[منطقة رابعة]');
    expect(landmarks(world)[0]?.place).toBeNull();
    expect(revealName(world, orphan)).toBe('[منطقة رابعة]');
    expect(revealName(world, { ...orphan, region_id: 'T42' })).toBe('T42');
  });

  it('lists every learned insight, the latest first, with where it shows', () => {
    const items = learned(WORLD);

    expect(items.map((item) => item.insight.id)).toEqual(['9003', '9002', '9001']);
    expect(items[0]?.spot?.id).toBe('6003');
    // An insight whose region had no room shows at its region's landmark.
    const crowded = {
      ...WORLD,
      places: [
        { ...PLACE_TWO, insights: [{ ...PLACE_TWO.insights[0], reveal_id: null }] },
      ] as (typeof WORLD)['places'],
    };
    expect(learned(crowded)[0]?.spot?.id).toBe('6002');
  });

  it('keeps for later only the reveals the world has not played', () => {
    expect(pendingReveals(WORLD)).toEqual([]);
    expect(pendingReveals(WORLD_JUST_LEARNED).map((reveal) => reveal.id)).toEqual(['6001']);
    expect(revealName(WORLD, REVEALS[1] as Reveal)).toBe(PLACE_TWO.name);
  });

  it('gives each theme its colour and each insight its route', () => {
    expect(THEME_COLORS.water).toBe('#83e1d5');
    expect(insightHref('9001')).toBe('/insight/9001');
  });
});

describe('the announcement after a reveal plays', () => {
  it('names the landmarks that appeared, or the region that widened, or nothing', () => {
    expect(announcement(WORLD, ['6001', '6002'])).toBe(
      `حُفظت بصائرك، وانكشف في عالمك: ${PLACE_ONE.name}، ${PLACE_TWO.name}.`
    );
    expect(announcement(WORLD, ['6003'])).toBe(`حُفظت بصيرتك، واتّسع ${PLACE_TWO.name}.`);
    expect(announcement(WORLD, ['6999'])).toBe('');
  });
});
