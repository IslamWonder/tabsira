import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TextArea } from './text-area';

describe('TextArea', () => {
  it('ties its label, hint, count and error to the field', () => {
    render(
      <TextArea label="[الحقل]" hint="[تلميح]" error="[خطأ]" maxChars={10} value="أب" rows={2} />
    );
    const field = screen.getByLabelText('[الحقل]');
    expect(field).toHaveAttribute('rows', '2');
    expect(field).toBeInvalid();
    expect(field).toHaveAccessibleDescription('[تلميح] 2 / 10 [خطأ]');
    expect(screen.getByText('2 / 10')).toHaveClass('text-fg-muted');
  });

  it('counts characters, not code units, and marks the field when the limit is passed', () => {
    render(<TextArea label="[الحقل]" maxChars={2} value="😀😀😀" />);
    const field = screen.getByLabelText('[الحقل]');
    expect(field).toBeInvalid();
    expect(field).toHaveClass('border-danger');
    expect(screen.getByText('3 / 2')).toHaveClass('text-danger');
  });

  it('describes nothing when there is no hint, no limit and no error', () => {
    render(<TextArea label="[آخر]" error="" />);
    const field = screen.getByLabelText('[آخر]');
    expect(field).not.toHaveAttribute('aria-describedby');
    expect(field).not.toHaveAttribute('aria-invalid');
    expect(field).toHaveAttribute('rows', '4');
    expect(field).toHaveClass('border-field');
  });
});
