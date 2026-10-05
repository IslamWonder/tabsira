import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { mockApi } from '@/test/api';
import { PLACE_ONE, WORLD, WORLD_JUST_LEARNED } from '@/test/world';
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

describe('useWorld, quietly', () => {
  it('keeps what is on screen when a quiet reload fails, and marks reveals shown before the API hears', async () => {
    let calls = 0;
    mockApi({
      'GET /world': () => {
        calls += 1;
        return calls === 1
          ? { body: WORLD_JUST_LEARNED }
          : { status: 503, body: { error: 'service_unavailable', detail: 'x' } };
      },
      'POST /world/reveals/shown': 'network-error',
    });
    const { result } = renderHook(() => useWorld());
    act(() => result.current.markShown(['6001']));
    await waitFor(() => expect(result.current.load.status).toBe('ready'));
    const ready = result.current.load;
    expect(ready.status === 'ready' && ready.world.reveals[0]?.shown).toBe(true);

    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(calls).toBe(2));

    expect(result.current.load).toBe(ready);
  });

  it('does not read the world again while the page is hidden', async () => {
    let calls = 0;
    mockApi({
      'GET /world': () => {
        calls += 1;
        return { body: WORLD };
      },
    });
    renderHook(() => useWorld());
    await waitFor(() => expect(calls).toBe(1));
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(calls).toBe(1);
  });
});
