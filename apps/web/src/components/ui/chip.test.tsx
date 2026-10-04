import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CheckIcon } from '@/components/icons';
import { Chip } from './chip';

describe('Chip', () => {
  it.each(['neutral', 'primary', 'quran', 'sunnah', 'glass'] as const)(
    'renders the %s tone as static text',
    (tone) => {
      render(<Chip tone={tone}>وسم</Chip>);
      const chip = screen.getByText('وسم');
      expect(chip.tagName).toBe('SPAN');
      expect(screen.queryByRole('button')).toBeNull();
    }
  );

  it('hides its icon from assistive technology', () => {
    render(
      <Chip icon={<CheckIcon />} className="extra">
        مثال
      </Chip>
    );
    const chip = screen.getByText('مثال');
    expect(chip).toHaveClass('extra');
    expect(chip.firstElementChild).toHaveAttribute('aria-hidden', 'true');
  });
});
