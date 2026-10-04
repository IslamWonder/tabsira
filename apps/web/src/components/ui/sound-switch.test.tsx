import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { SOUND_STORAGE_KEY } from '@/preferences/sound';
import { SoundSwitch } from './sound-switch';

describe('SoundSwitch', () => {
  it('is a named, described switch, on by default, that turns the sound off and on', async () => {
    render(<SoundSwitch className="extra" />);
    const toggle = screen.getByRole('switch', { name: 'المؤثر الصوتي' });
    expect(toggle).toBeChecked();
    expect(toggle).toHaveAccessibleDescription(/هذا الجهاز/);
    await userEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(window.localStorage.getItem(SOUND_STORAGE_KEY)).toBe('off');
    await userEvent.click(toggle);
    expect(toggle).toBeChecked();
  });
});
