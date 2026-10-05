import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { setSoundEnabled } from '@/preferences/sound';
import { type SoundMoment, useSceneSound } from './use-scene-sound';

const player = vi.hoisted(() => ({ loopSound: vi.fn(), endLoop: vi.fn(), stopSound: vi.fn() }));
vi.mock('@/lib/sound/player', () => player);

const URL = '/sounds/ontology/E006';

function follow(url: string | null, moment: SoundMoment) {
  return renderHook(({ url, moment }) => useSceneSound(url, moment), {
    initialProps: { url, moment },
  });
}

beforeEach(() => {
  window.localStorage.clear();
  for (const call of Object.values(player)) {
    call.mockReset();
  }
});

describe('useSceneSound', () => {
  it('loops the sound once it is known, and ends it with its loop when the run ends', () => {
    const { rerender, unmount } = follow(null, 'running');
    expect(player.loopSound).not.toHaveBeenCalled();
    rerender({ url: URL, moment: 'running' });
    expect(player.loopSound).toHaveBeenCalledWith(URL);
    rerender({ url: URL, moment: 'ended' });
    expect(player.endLoop).toHaveBeenCalledOnce();
    expect(player.stopSound).not.toHaveBeenCalled();
    // Leaving the page, for the insight and its verse, fades it out.
    unmount();
    expect(player.stopSound).toHaveBeenCalledOnce();
  });

  it('fades the sound out at once when the run fails', () => {
    const { rerender } = follow(URL, 'running');
    rerender({ url: URL, moment: 'failed' });
    expect(player.stopSound).toHaveBeenCalledOnce();
    expect(player.endLoop).not.toHaveBeenCalled();
  });

  it('starts again when switched on during the run, never after it', () => {
    setSoundEnabled(false);
    const { rerender } = follow(URL, 'running');
    expect(player.loopSound).not.toHaveBeenCalled();
    act(() => setSoundEnabled(true));
    expect(player.loopSound).toHaveBeenCalledOnce();

    rerender({ url: URL, moment: 'ended' });
    act(() => setSoundEnabled(false));
    act(() => setSoundEnabled(true));
    expect(player.loopSound).toHaveBeenCalledOnce();
  });

  it('plays nothing for a finished scan opened later', () => {
    follow(URL, 'ended');
    expect(player.loopSound).not.toHaveBeenCalled();
  });
});
