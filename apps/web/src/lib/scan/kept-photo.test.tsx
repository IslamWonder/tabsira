import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { insightOut } from '@/test/scan';
import { useKeptPhoto } from './kept-photo';

const ID = '110000000000000002';

describe('useKeptPhoto', () => {
  it('says a photo is kept only when the owner view says so', async () => {
    mockApi({
      [`GET /insights/${ID}`]: {
        body: insightOut({ image: { sensitive: false, url: null, has_photo: true } }),
      },
    });
    const { result } = renderHook(() => useKeptPhoto(ID, true));
    await waitFor(() => expect(result.current).toBe(true));
  });

  it('asks nothing for a guest or without an insight, and treats a failure as no photo', async () => {
    const api = mockApi({ [`GET /insights/${ID}`]: apiError(404, 'NOT_FOUND') });
    const guest = renderHook(() => useKeptPhoto(ID, false));
    const none = renderHook(() => useKeptPhoto(null, true));
    expect(guest.result.current).toBe(false);
    expect(none.result.current).toBe(false);
    expect(api.requests).toHaveLength(0);
    const failed = renderHook(() => useKeptPhoto(ID, true));
    await waitFor(() => expect(api.requests).toHaveLength(1));
    expect(failed.result.current).toBe(false);
  });

  it('ignores an answer that arrives after the screen left', async () => {
    let answer: (() => void) | null = null;
    mockApi({
      [`GET /insights/${ID}`]: () =>
        new Promise((resolve) => {
          answer = () =>
            resolve({
              body: insightOut({ image: { sensitive: false, url: null, has_photo: true } }),
            });
        }),
    });
    const { result, unmount } = renderHook(() => useKeptPhoto(ID, true));
    await waitFor(() => expect(answer).not.toBeNull());
    unmount();
    (answer as (() => void) | null)?.();
    expect(result.current).toBe(false);
  });
});
