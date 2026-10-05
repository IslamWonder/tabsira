import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LANDMARK_ICONS, LandmarkIcon } from './landmark-icons';

describe('LandmarkIcon', () => {
  it('draws every landmark of layout 1, decoratively, in currentColor', () => {
    expect(LANDMARK_ICONS).toHaveLength(16);
    for (const icon of LANDMARK_ICONS) {
      const { container, unmount } = render(<LandmarkIcon icon={icon} />);
      const svg = container.querySelector('svg') as SVGElement;
      expect(svg).toHaveAttribute('aria-hidden', 'true');
      expect(svg).toHaveAttribute('stroke', 'currentColor');
      expect(svg.children.length).toBeGreaterThan(0);
      unmount();
    }
  });

  it('draws a plain star for a landmark a later layout names', () => {
    const { container } = render(<LandmarkIcon icon="volcano" />);
    expect(container.querySelectorAll('path')).toHaveLength(1);
  });
});
