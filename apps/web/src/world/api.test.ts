import { describe, expect, it } from 'vitest';
import { loadProgress } from '@/progress/api';
import { mockApi } from '@/test/api';
import { PLACE_TWO, PROGRESS, TREASURE, WORLD } from '@/test/world';
import { loadWorld, revealTreasure, visitPlace } from './api';

describe('the world calls', () => {
  it('loads the map', async () => {
    mockApi({ 'GET /world': { body: WORLD } });
    const result = await loadWorld();
    expect(result).toMatchObject({ ok: true, data: WORLD });
  });

  it('visits a place by its string id, kept whole', async () => {
    const api = mockApi({ 'POST /world/places/9007199254740993/visit': { body: PLACE_TWO } });
    const result = await visitPlace('9007199254740993');
    expect(result.ok).toBe(true);
    expect(api.requests).toHaveLength(1);
  });

  it('reveals a treasure by its string id', async () => {
    mockApi({ 'POST /world/treasures/8001/reveal': { body: TREASURE } });
    expect(await revealTreasure('8001')).toMatchObject({ ok: true, data: TREASURE });
  });

  it('asks for the practice in the device time zone', async () => {
    const api = mockApi({ 'GET /me/progress': { body: PROGRESS } });
    await loadProgress('Africa/Tunis');
    expect(new URL(api.requests[0]?.url ?? '').searchParams.get('tz')).toBe('Africa/Tunis');
  });
});
