import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { readSoundEnabled } from '@/preferences/sound';
import { SoundToggle } from './sound-toggle';

describe('SoundToggle', () => {
  it('is a toggle button that says the state and flips it', async () => {
    render(<SoundToggle className="extra" />);
    const button = screen.getByRole('button', { name: 'المؤثر الصوتي' });
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(button).toHaveAttribute('title', 'المؤثر الصوتي: مفعّل');
    expect(button).toHaveClass('extra');
    await userEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(button).toHaveAttribute('title', 'المؤثر الصوتي: مُوقَف');
    expect(readSoundEnabled()).toBe(false);
    await userEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(readSoundEnabled()).toBe(true);
  });
});
