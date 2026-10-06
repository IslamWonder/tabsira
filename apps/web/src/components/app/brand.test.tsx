import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Brand, SHINE_TIMING } from './brand';

const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms));
const mark = () => screen.getByRole('img', { name: 'تبصرة' });

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('the top bar mark', () => {
  it('leads home, writes itself in once, and keeps its light behind it decorative', () => {
    const { container } = render(<Brand />);
    expect(screen.getByRole('link')).toHaveAttribute('href', '/');
    expect(mark()).toHaveClass('fx-logo-glow');
    expect(mark()).not.toHaveAttribute('data-shine');
    expect(container.querySelectorAll('.fx-logo-spark')).toHaveLength(4);
    expect(
      container.querySelector('.fx-logo-ring')?.closest('[aria-hidden="true"]')
    ).not.toBeNull();
  });

  it('shines again only after a long stillness, a new name each time, three times at most', () => {
    render(<Brand />);
    const seen: (string | null)[] = [];
    for (let shine = 0; shine < SHINE_TIMING.max + 1; shine += 1) {
      wait(SHINE_TIMING.idleMs);
      seen.push(mark().getAttribute('data-shine'));
      wait(SHINE_TIMING.hintMs);
    }
    expect(seen).toEqual(['a', 'b', 'a', 'a']);
  });

  it('never shines while the reader is busy', () => {
    render(<Brand />);
    for (let tap = 0; tap < 3; tap += 1) {
      wait(SHINE_TIMING.idleMs - 1000);
      act(() => {
        window.dispatchEvent(new Event('pointerdown'));
      });
    }
    expect(mark()).not.toHaveAttribute('data-shine');
  });
});
