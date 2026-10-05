import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EMPTY_FILTERS } from '@/atlas/types';
import { mockApi } from '@/test/api';
import { FEATURE } from '@/test/atlas';
import { useAtlasData } from './use-atlas-data';

const WINDOW = { west: 9, south: 35, east: 11, north: 37 };
const VIEW = { center: [10, 36] as [number, number], zoom: 8 };

describe('useAtlasData', () => {
  it('has nothing to load before the map reports a window, and nothing more after the last page', async () => {
    const api = mockApi({
      'GET /atlas/clusters': {
        body: { type: 'FeatureCollection', features: [], truncated: false },
      },
      'GET /atlas/entries/page': { body: { items: [FEATURE], next_cursor: null, total: 1 } },
    });
    const { result } = renderHook(() => useAtlasData(EMPTY_FILTERS));
    await act(() => result.current.loadMore());
    expect(api.requests).toHaveLength(0);

    act(() => result.current.onMoved(WINDOW, false, VIEW));
    await waitFor(() => expect(result.current.list.status).toBe('ready'));
    await act(() => result.current.loadMore());
    // The last page had no cursor: no further request.
    expect(api.requests.filter((r) => r.url.includes('/atlas/entries/page'))).toHaveLength(1);
    expect(result.current.listCentre).toEqual([10, 36]);
  });
});
