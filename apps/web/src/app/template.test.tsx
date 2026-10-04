import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Template from './template';

describe('route template', () => {
  it('fades the page in under a gold light sweep, without transforming the page', () => {
    const { container } = render(
      <Template>
        <p>[صفحة]</p>
      </Template>
    );
    const sweep = container.firstElementChild as HTMLElement;
    expect(sweep).toHaveAttribute('aria-hidden', 'true');
    expect(sweep.className).toContain('fx-route');
    const page = screen.getByText('[صفحة]').parentElement as HTMLElement;
    expect(page.className).toBe('motion-safe:animate-fade-in');
  });
});
