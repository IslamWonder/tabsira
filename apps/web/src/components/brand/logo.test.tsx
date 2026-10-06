import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Logo, LogoMark, writingOrder } from './logo';
import { LOGO, MARK } from './logo-paths';

describe('the logo', () => {
  it('draws the mark in the brand token, named when it stands for the product', () => {
    render(<LogoMark title="تبصرة" className="h-12" />);
    const mark = screen.getByRole('img', { name: 'تبصرة' });
    expect(mark).toHaveClass('text-brand', 'h-12');
    expect(mark.getAttribute('fill')).toBe('currentColor');
    expect(mark.querySelectorAll('path')).toHaveLength(MARK.paths.length);
    expect(mark.style.aspectRatio).toBe('372 / 372.5');
  });

  it('is decorative without a name, and the full logo carries the Latin name', () => {
    const { container } = render(<Logo />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg?.querySelector('title')).toBeNull();
    expect(svg?.querySelectorAll('path')).toHaveLength(LOGO.paths.length);
    expect(LOGO.paths.length).toBeGreaterThan(MARK.paths.length);
  });

  it('stays still unless asked to write itself in', () => {
    const { container } = render(<LogoMark />);
    expect(container.querySelector('.fx-logo-stroke')).toBeNull();
  });

  it('writes the mark in from right to left, each stroke from where its outline starts', () => {
    const { container } = render(<LogoMark entrance />);
    const strokes = container.querySelectorAll<SVGPathElement>('path.fx-logo-stroke');
    expect(strokes).toHaveLength(MARK.paths.length);
    const order = writingOrder(MARK);
    expect(strokes[0]?.style.getPropertyValue('--fx-x')).toBe(String(order[0]));
    expect(order.every((x) => x >= 0 && x <= 1)).toBe(true);
  });

  it('orders the strokes by where they start: the rightmost first', () => {
    const shape = { viewBox: '0 0 100 100', paths: ['M100 0Z', 'M50 0Z', 'M0 0Z', 'M150 0Z', 'Z'] };
    expect(writingOrder(shape)).toEqual([0, 0.5, 1, 0, 0]);
  });
});
