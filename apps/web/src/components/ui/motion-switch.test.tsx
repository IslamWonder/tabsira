import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MOTION_STORAGE_KEY } from '@/preferences/motion';
import { MotionSwitch } from './motion-switch';

describe('MotionSwitch', () => {
  it('is a named, described switch, on by default', () => {
    render(<MotionSwitch className="extra" />);
    const toggle = screen.getByRole('switch', { name: 'الحركة الزخرفية' });
    expect(toggle).toBeChecked();
    expect(toggle).toHaveAccessibleDescription(/تقليل الحركة/);
  });

  it('turns decorative motion off and on again, from the keyboard too', async () => {
    render(<MotionSwitch />);
    const toggle = screen.getByRole('switch');
    await userEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(window.localStorage.getItem(MOTION_STORAGE_KEY)).toBe('off');
    expect(document.documentElement.dataset.motion).toBe('reduce');
    toggle.focus();
    await userEvent.keyboard(' ');
    expect(toggle).toBeChecked();
  });
});
