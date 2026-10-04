import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Insight } from '@/lib/scan/api';
import { insightOut } from '@/test/scan';
import { useInsightSound } from './use-insight-sound';

const player = vi.hoisted(() => ({ playSound: vi.fn(), stopSound: vi.fn() }));
vi.mock('@/lib/sound/player', () => player);

beforeEach(() => {
  player.playSound.mockReset();
  player.stopSound.mockReset();
});

describe('useInsightSound', () => {
  it('plays the sound of the insight once, and stops it on leaving', () => {
    const insight = insightOut({ sound_url: '/sounds/ontology/E006' });
    const { rerender, unmount } = renderHook(({ shown }) => useInsightSound(shown), {
      initialProps: { shown: insight },
    });
    rerender({ shown: { ...insight, completed_at: '2026-10-04T09:00:00Z' } });
    expect(player.playSound).toHaveBeenCalledTimes(1);
    expect(player.playSound).toHaveBeenCalledWith('/sounds/ontology/E006');
    unmount();
    expect(player.stopSound).toHaveBeenCalledTimes(1);
  });

  it('plays nothing while the insight loads or when it has no sound', () => {
    const { rerender } = renderHook(({ shown }) => useInsightSound(shown), {
      initialProps: { shown: null as Insight | null },
    });
    rerender({ shown: insightOut({ sound_url: null }) });
    expect(player.playSound).not.toHaveBeenCalled();
    expect(player.stopSound).not.toHaveBeenCalled();
  });
});
