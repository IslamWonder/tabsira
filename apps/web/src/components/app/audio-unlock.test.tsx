import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AudioUnlock } from './audio-unlock';

const player = vi.hoisted(() => ({ armAudioUnlock: vi.fn() }));
vi.mock('@/lib/sound/player', () => player);

describe('AudioUnlock', () => {
  it('arms the audio unlock once the page is up, and renders nothing', () => {
    const { container } = render(<AudioUnlock />);
    expect(player.armAudioUnlock).toHaveBeenCalledOnce();
    expect(container).toBeEmptyDOMElement();
  });
});
