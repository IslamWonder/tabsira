import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EmptyStage } from './empty-stage';

describe('EmptyStage', () => {
  it('shows the icon in a beacon over the pattern, with no sample content', () => {
    const { container } = render(<EmptyStage icon={<span data-testid="icon" />} />);
    expect(screen.getByTestId('icon')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toBe('');
  });
});
