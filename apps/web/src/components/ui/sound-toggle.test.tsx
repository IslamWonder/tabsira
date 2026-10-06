import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { readSoundEnabled } from '@/preferences/sound';
import { SoundToggle } from './sound-toggle';

const playing = vi.hoisted(() => ({ now: false }));

vi.mock('@/lib/sound/player', async (original) => ({
  ...(await original<typeof import('@/lib/sound/player')>()),
  useSoundPlaying: () => playing.now,
}));

afterEach(() => {
  playing.now = false;
  window.localStorage.clear();
});

describe('SoundToggle', () => {
  it('is a toggle button that says the state and flips it', async () => {
    render(<SoundToggle className="extra" />);
    const button = screen.getByRole('button', { name: 'المؤثر الصوتي' });
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(button).toHaveAttribute('title', 'المؤثر الصوتي: مفعّل');
    expect(button.parentElement).toHaveClass('extra');
    expect(button.parentElement).not.toHaveClass('relative');
    await userEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(button).toHaveAttribute('title', 'المؤثر الصوتي: مُوقَف');
    expect(readSoundEnabled()).toBe(false);
    await userEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(readSoundEnabled()).toBe(true);
  });

  it('shows a sound being heard with moving bars and a ring, and says so', async () => {
    playing.now = true;
    const { container } = render(<SoundToggle />);
    const button = screen.getByRole('button', { name: 'المؤثر الصوتي' });
    expect(button).toHaveAttribute('title', 'المؤثر الصوتي: يُسمع الآن');
    expect(button.parentElement).toHaveClass('relative');
    expect(container.querySelectorAll('.fx-eq-bar')).toHaveLength(3);
    expect(screen.getByTestId('sound-ring')).toHaveAttribute('aria-hidden', 'true');
    // Turned off, nothing says it is heard, even before the fade out ends.
    await userEvent.click(button);
    expect(button).toHaveAttribute('title', 'المؤثر الصوتي: مُوقَف');
    expect(screen.queryByTestId('sound-ring')).toBeNull();
    expect(container.querySelector('.fx-eq-bar')).toBeNull();
  });
});
