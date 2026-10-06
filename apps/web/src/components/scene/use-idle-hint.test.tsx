import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SceneInsightList } from './scene-insight-list';
import { HINT_MS, IDLE_MS, MAX_HINTS } from './use-idle-hint';

const POINTS = [
  { id: 'a', x: 0.2, y: 0.5, title: '[أولى]', tone: 'gold' as const },
  { id: 'b', x: 0.5, y: 0.7, title: '[ثانية]', tone: 'emerald' as const },
];
const HINT = 'اختر بصيرة لتفتحها كاملة';
const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms));

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('the idle hint of a fresh list of insights', () => {
  it('waits for a reader who does nothing, says it a moment, and comes back once at most', () => {
    render(<SceneInsightList points={POINTS} onSelect={vi.fn()} invite />);
    expect(screen.queryByText(HINT)).toBeNull();
    wait(IDLE_MS);
    // A toast in the page's status line: heard once by a screen reader, moving nothing.
    expect(screen.getByRole('status')).toHaveTextContent(HINT);
    wait(HINT_MS);
    expect(screen.queryByText(HINT)).toBeNull();
    for (let shown = 1; shown < MAX_HINTS; shown += 1) {
      wait(IDLE_MS);
      expect(screen.getByText(HINT)).toBeInTheDocument();
      wait(HINT_MS);
    }
    wait(IDLE_MS * 3);
    expect(screen.queryByText(HINT)).toBeNull();
  });

  it('never interrupts a reader who taps, types or scrolls, and hides at once on a tap', () => {
    render(<SceneInsightList points={POINTS} onSelect={vi.fn()} invite />);
    for (const name of ['pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll']) {
      wait(IDLE_MS - 1000);
      act(() => {
        window.dispatchEvent(new Event(name));
      });
    }
    expect(screen.queryByText(HINT)).toBeNull();
    wait(IDLE_MS);
    expect(screen.getByText(HINT)).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new Event('pointerdown'));
    });
    expect(screen.queryByText(HINT)).toBeNull();
  });

  it('calls with every row as the list shows, and replays the call with the hint', () => {
    const { container } = render(<SceneInsightList points={POINTS} onSelect={vi.fn()} invite />);
    const sheens = () => Array.from(container.querySelectorAll<HTMLElement>('.fx-sheen'));
    expect(sheens()).toHaveLength(2);
    // One row after the other.
    expect(sheens().map((sheen) => sheen.style.getPropertyValue('--fx-delay'))).toEqual([
      '400ms',
      '680ms',
    ]);
    expect(container.querySelectorAll('.fx-dot-ring')).toHaveLength(2);
    const first = sheens()[0];
    wait(IDLE_MS);
    // Remounted, so the animation plays again.
    expect(sheens()[0]).not.toBe(first);
  });

  it('stays quiet when it is only a list, and stops when the page leaves', () => {
    const { container, unmount, rerender } = render(
      <SceneInsightList points={POINTS} onSelect={vi.fn()} />
    );
    expect(container.querySelector('.fx-sheen')).toBeNull();
    wait(IDLE_MS * 2);
    expect(screen.queryByText(HINT)).toBeNull();
    rerender(<SceneInsightList points={POINTS} onSelect={vi.fn()} invite />);
    unmount();
    wait(IDLE_MS * 2);
    expect(screen.queryByText(HINT)).toBeNull();
  });
});
