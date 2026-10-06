import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCallChime } from './use-call-chime';

const player = vi.hoisted(() => ({ playChime: vi.fn() }));
vi.mock('@/lib/sound/player', () => player);

function follow(asking: boolean, running: boolean) {
  return renderHook(({ asking, running }) => useCallChime(asking, running), {
    initialProps: { asking, running },
  });
}

beforeEach(() => {
  player.playChime.mockReset();
});

describe('useCallChime', () => {
  it('chimes once when a watched run stops to ask, and again after the next run asks', () => {
    const { rerender } = follow(false, true);
    expect(player.playChime).not.toHaveBeenCalled();
    rerender({ asking: true, running: false });
    expect(player.playChime).toHaveBeenCalledOnce();
    rerender({ asking: true, running: false });
    expect(player.playChime).toHaveBeenCalledOnce();

    rerender({ asking: false, running: true });
    rerender({ asking: true, running: false });
    expect(player.playChime).toHaveBeenCalledTimes(2);
  });

  it('stays quiet for a scan opened later that already asks', () => {
    follow(true, false);
    expect(player.playChime).not.toHaveBeenCalled();
  });
});
