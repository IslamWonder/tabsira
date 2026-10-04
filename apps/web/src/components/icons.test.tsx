import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import * as icons from './icons';

describe('icons', () => {
  it.each(Object.entries(icons))('%s is decorative and drawn in currentColor', (_name, Icon) => {
    const { container } = render(<Icon />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('focusable', 'false');
    expect(svg).toHaveAttribute('stroke', 'currentColor');
  });

  it('lets the caller resize an icon', () => {
    const { container } = render(<icons.CheckIcon width="12" height="12" />);
    expect(container.querySelector('svg')).toHaveAttribute('width', '12');
  });
});
