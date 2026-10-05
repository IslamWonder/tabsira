import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Emblem, EmblemTile } from './emblem';
import { EMBLEMS, type EmblemName } from './emblem-data';

const NAMES = Object.keys(EMBLEMS) as EmblemName[];

describe('Emblem', () => {
  it.each(NAMES)(
    '%s is decorative, drawn in the colour of its text, from its own paths',
    (name) => {
      const { container } = render(<Emblem name={name} />);
      const svg = container.querySelector('svg') as SVGSVGElement;
      expect(svg).toHaveAttribute('aria-hidden', 'true');
      expect(svg).toHaveAttribute('focusable', 'false');
      expect(svg).toHaveAttribute('fill', 'currentColor');
      expect(svg).toHaveAttribute('viewBox', EMBLEMS[name].viewBox);
      expect(container.querySelectorAll('path')).toHaveLength(EMBLEMS[name].paths.length);
    }
  );

  it('keeps no colour of its own and fetches nothing', () => {
    for (const { paths } of Object.values(EMBLEMS)) {
      for (const d of paths) {
        expect(d).toMatch(/^[MmLlHhVvCcSsQqTtAaZz0-9 .-]+$/);
      }
    }
  });

  it('lets the caller resize it', () => {
    const { container } = render(<Emblem name="lantern" width="40" height="40" />);
    expect(container.querySelector('svg')).toHaveAttribute('width', '40');
  });
});

describe('EmblemTile', () => {
  it('frames the emblem, hidden from assistive technology, at two sizes', () => {
    const { container, rerender } = render(<EmblemTile name="treasure" className="extra" />);
    const tile = container.firstElementChild as HTMLElement;
    expect(tile).toHaveAttribute('aria-hidden', 'true');
    expect(tile).toHaveClass('size-12', 'extra');
    expect(tile.querySelector('svg')).toHaveAttribute('width', '26');
    rerender(
      <EmblemTile name="treasure" size="lg">
        <span data-testid="halo" />
      </EmblemTile>
    );
    expect(container.firstElementChild).toHaveClass('size-14');
    expect(container.querySelector('svg')).toHaveAttribute('width', '30');
    expect(container.querySelector('[data-testid="halo"]')).not.toBeNull();
  });
});
