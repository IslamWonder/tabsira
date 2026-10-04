import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mockApi } from '@/test/api';
import { PLACE_ONE, WORLD } from '@/test/world';
import { useWorld } from './use-world';

describe('useWorld', () => {
  it('replaces a place once the world is loaded, and leaves a world still loading alone', async () => {
    mockApi({ 'GET /world': { body: WORLD } });
    const { result } = renderHook(() => useWorld());
    act(() => result.current.replacePlace(PLACE_ONE));
    expect(result.current.load.status).toBe('loading');
    await waitFor(() => expect(result.current.load.status).toBe('ready'));
    const changed = { ...PLACE_ONE, name: '[اسم جديد]' };
    act(() => result.current.replacePlace(changed));
    const load = result.current.load;
    expect(load.status === 'ready' && load.world.places[0]?.name).toBe('[اسم جديد]');
  });
});
