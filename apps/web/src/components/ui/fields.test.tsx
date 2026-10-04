import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ChoiceChecks, ChoiceGroup } from './choice-group';
import { Notice } from './notice';
import { SwitchField } from './switch-field';
import { SwitchRow } from './switch-row';
import { TextField } from './text-field';

describe('TextField', () => {
  it('ties its label, hint and error to the input', () => {
    render(<TextField label="[الحقل]" hint="[تلميح]" error="[خطأ]" className="extra" />);
    const input = screen.getByLabelText('[الحقل]');
    expect(input).toHaveAccessibleDescription('[تلميح] [خطأ]');
    expect(input).toBeInvalid();
    render(<TextField label="[آخر]" error="" />);
    expect(screen.getByLabelText('[آخر]')).not.toHaveAttribute('aria-describedby');
  });

  it('shows and hides a password', async () => {
    render(<TextField label="[كلمة]" type="password" revealable />);
    const input = screen.getByLabelText('[كلمة]');
    await userEvent.click(screen.getByRole('button', { name: 'أظهر كلمة المرور' }));
    expect(input).toHaveAttribute('type', 'text');
    const hide = screen.getByRole('button', { name: 'أخفِ كلمة المرور' });
    expect(hide).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(hide);
    expect(input).toHaveAttribute('type', 'password');
  });
});

describe('Notice', () => {
  it('carries its state in a mark as well as a colour', () => {
    const { container } = render(
      <>
        <Notice tone="success">[تم]</Notice>
        <Notice tone="error">[خطأ]</Notice>
        <Notice tone="info">[معلومة]</Notice>
      </>
    );
    expect(container.querySelectorAll('svg')).toHaveLength(1);
    expect(container.querySelectorAll('[aria-hidden="true"]').length).toBeGreaterThanOrEqual(3);
  });
});

describe('SwitchRow', () => {
  it('is a labelled switch that waits while a change is saved', async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <SwitchRow label="[خيار]" hint="[أثره]" checked={false} onChange={onChange} />
    );
    const toggle = screen.getByRole('switch', { name: '[خيار]' });
    expect(toggle).toHaveAccessibleDescription('[أثره]');
    await userEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith(true);
    rerender(<SwitchRow label="[خيار]" checked onChange={onChange} busy />);
    await userEvent.click(toggle);
    expect(onChange).toHaveBeenCalledOnce();
    expect(toggle).toHaveAttribute('aria-busy', 'true');
    rerender(<SwitchRow label="[خيار]" checked onChange={onChange} disabled />);
    expect(toggle).toBeDisabled();
  });
});

function Harness() {
  const [one, setOne] = useState<'a' | 'b'>('a');
  const [many, setMany] = useState<Array<'x' | 'y' | 'z'>>([]);
  return (
    <>
      <ChoiceGroup
        legend="[واحد]"
        hint="[تلميح]"
        options={[
          { value: 'a', label: '[أ]' },
          { value: 'b', label: '[ب]' },
        ]}
        value={one}
        onChange={setOne}
      />
      <ChoiceChecks
        legend="[عدة]"
        options={[
          { value: 'x', label: '[س]' },
          { value: 'y', label: '[ص]' },
          { value: 'z', label: '[ع]' },
        ]}
        values={many}
        onChange={setMany}
      />
      <output>{many.join(',')}</output>
    </>
  );
}

describe('ChoiceGroup and ChoiceChecks', () => {
  it('pick one, or several in the order offered', async () => {
    render(<Harness />);
    expect(screen.getByRole('group', { name: '[واحد]' })).toHaveAccessibleDescription('[تلميح]');
    await userEvent.click(screen.getByRole('radio', { name: '[ب]' }));
    expect(screen.getByRole('radio', { name: '[ب]' })).toBeChecked();
    await userEvent.click(screen.getByRole('checkbox', { name: '[ع]' }));
    await userEvent.click(screen.getByRole('checkbox', { name: '[س]' }));
    expect(document.querySelector('output')?.textContent).toBe('x,z');
    await userEvent.click(screen.getByRole('checkbox', { name: '[س]' }));
    expect(document.querySelector('output')?.textContent).toBe('z');
  });
});

describe('SwitchField', () => {
  it('is a real checkbox with role switch, posted with its form', async () => {
    const onChange = vi.fn();
    render(
      <form>
        <SwitchField name="analytics" label="[فئة]" checked={false} onChange={onChange} />
        <SwitchField
          name="behaviour"
          label="[أخرى]"
          hint="[وصف]"
          checked
          disabled
          onChange={onChange}
        />
      </form>
    );
    const toggle = screen.getByRole('switch', { name: '[فئة]' });
    expect(toggle).toHaveAttribute('type', 'checkbox');
    expect(toggle).not.toHaveAttribute('aria-describedby');
    await userEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith(true);
    const fixed = screen.getByRole('switch', { name: '[أخرى]' });
    expect(fixed).toHaveAccessibleDescription('[وصف]');
    expect(fixed).toBeDisabled();
    expect(new FormData(fixed.closest('form') as HTMLFormElement).get('analytics')).toBeNull();
  });
});
