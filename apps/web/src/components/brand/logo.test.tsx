import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Logo, LogoMark } from './logo';
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
});
