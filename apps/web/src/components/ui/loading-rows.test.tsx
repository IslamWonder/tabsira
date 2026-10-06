import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LoadingRows } from './loading-rows';

describe('LoadingRows', () => {
  it('tells screen readers it is loading and draws empty, hidden shapes', () => {
    const { container } = render(<LoadingRows label="[يحمّل]" />);
    expect(screen.getByRole('status')).toHaveTextContent('[يحمّل]');
    const shapes = container.querySelectorAll('.fx-placeholder');
    expect(shapes).toHaveLength(3);
    for (const shape of shapes) {
      expect(shape).toHaveAttribute('aria-hidden', 'true');
      expect(shape).toBeEmptyDOMElement();
      expect(shape.className).toContain('h-20');
    }
  });

  it('takes the number and height of the rows', () => {
    const { container } = render(
      <LoadingRows label="[يحمّل]" rows={2} rowClassName="h-12" className="[extra]" />
    );
    const shapes = container.querySelectorAll('.fx-placeholder');
    expect(shapes).toHaveLength(2);
    expect(shapes[0]?.className).toContain('h-12');
    expect(screen.getByRole('status').className).toContain('[extra]');
  });
});
