import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CheckboxField } from './checkbox-field';

describe('CheckboxField', () => {
  it('is a native checkbox with its label and hint, and reports each change', async () => {
    const onChange = vi.fn();
    render(<CheckboxField label="[خيار]" hint="[ما يفعله]" checked={false} onChange={onChange} />);
    const box = screen.getByRole('checkbox', { name: '[خيار]' });
    expect(box).not.toBeChecked();
    expect(box).toHaveAccessibleDescription('[ما يفعله]');
    await userEvent.click(box);
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('works without a hint and can be disabled', async () => {
    const onChange = vi.fn();
    render(<CheckboxField label="[خيار]" checked={true} onChange={onChange} disabled />);
    const box = screen.getByRole('checkbox', { name: '[خيار]' });
    expect(box).toBeChecked();
    expect(box).toBeDisabled();
    expect(box).not.toHaveAttribute('aria-describedby');
    await userEvent.click(box);
    expect(onChange).not.toHaveBeenCalled();
  });
});
