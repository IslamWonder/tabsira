import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { InsightPoint, type InsightPointProps } from './insight-point';

function renderPoint(overrides: Partial<InsightPointProps> = {}) {
  const onSelect = vi.fn();
  render(
    <InsightPoint
      id="rain"
      title="[عنوان]"
      glimpse="[لمحة]"
      left={30}
      top={55}
      vertical="below"
      positionLabel="يسار وسط الصورة"
      onSelect={onSelect}
      {...overrides}
    />
  );
  return { onSelect, button: screen.getByRole('button') };
}

describe('InsightPoint', () => {
  it('is one real button named by its title and described by its glimpse and place', async () => {
    const { button, onSelect } = renderPoint();
    expect(button).toHaveAccessibleName('[عنوان]');
    expect(button).toHaveAccessibleDescription('[لمحة] يسار وسط الصورة');
    await userEvent.click(button);
    expect(onSelect).toHaveBeenCalledWith('rain');
  });

  it('works from the keyboard', async () => {
    const { button, onSelect } = renderPoint();
    button.focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard(' ');
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it('centres its orb on the point with the label below', () => {
    const { button } = renderPoint();
    expect(button.style.left).toBe('30%');
    expect(button.style.top).toBe('55%');
    expect(button.style.transform).toBe('translate(-50%, -28px)');
    expect(button).toHaveClass('flex-col', 'items-center');
  });

  it('calls with two rings and breathes, with its own delay', () => {
    const { button } = renderPoint({ tone: 'emerald', delay: 1.2 });
    const rings = button.querySelectorAll('[class*="fx-ring"]');
    expect(rings).toHaveLength(2);
    expect((rings[1] as HTMLElement).style.animationDelay).toBe('2s');
    const halo = button.querySelector('[class*="animate-breathe"]') as HTMLElement;
    expect(halo.style.animationDelay).toBe('1.2s');
  });

  it('grows its label toward the middle near a side', () => {
    const { button } = renderPoint({ horizontal: 'toRight' });
    expect(button.style.transform).toBe('translate(-28px, -28px)');
    expect(button).toHaveClass('items-end');
  });

  it('grows its label leftward near the right side', () => {
    const { button } = renderPoint({ horizontal: 'toLeft' });
    expect(button.style.transform).toBe('translate(calc(-100% + 28px), -28px)');
  });

  it('hangs its label above in the lower half, and rests once chosen', () => {
    const { button } = renderPoint({ vertical: 'above', selected: true, glimpse: undefined });
    expect(button.style.transform).toBe('translate(-50%, calc(-100% + 28px))');
    expect(button).toHaveClass('flex-col-reverse');
    expect(button).toHaveAttribute('aria-current', 'true');
    expect(button.querySelectorAll('[class*="fx-ring"]')).toHaveLength(0);
    expect(button).toHaveAccessibleDescription('يسار وسط الصورة');
  });
});
