import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { GlassPanel } from './glass-panel';

describe('GlassPanel', () => {
  it('is a padded glass div by default', () => {
    render(<GlassPanel data-testid="panel">محتوى</GlassPanel>);
    const panel = screen.getByTestId('panel');
    expect(panel.tagName).toBe('DIV');
    expect(panel).toHaveClass('glass', 'p-5');
  });

  it('renders the chosen element and tone, without padding when asked', () => {
    render(
      <GlassPanel as="section" tone="quran" padded={false} aria-label="القرآن">
        محتوى
      </GlassPanel>
    );
    const panel = screen.getByRole('region', { name: 'القرآن' });
    expect(panel.tagName).toBe('SECTION');
    expect(panel).not.toHaveClass('p-5');
    expect(panel.className).toContain('--quran-glow');
  });

  it('can be an RPG window with a gold double rule and khatam corners', () => {
    const { container } = render(
      <GlassPanel ornate data-testid="panel">
        محتوى
      </GlassPanel>
    );
    expect(screen.getByTestId('panel')).toHaveClass('fx-ornate', 'fx-ornate-glow');
    expect(container.querySelectorAll('.fx-corner')).toHaveLength(4);
  });

  it.each(['neutral', 'sunnah', 'primary'] as const)('has a %s tone', (tone) => {
    render(
      <GlassPanel as="article" tone={tone} data-testid="panel">
        محتوى
      </GlassPanel>
    );
    expect(screen.getByTestId('panel').tagName).toBe('ARTICLE');
  });
});
