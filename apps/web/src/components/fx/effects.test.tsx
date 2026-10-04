import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { BURST_EVENT } from './burst';
import { celebrate, VICTORY_EVENT } from './celebrate';
import { Flash } from './flash';
import { FocusMarker } from './focus-marker';
import { GeometricPattern } from './geometric-pattern';
import { OrnamentDivider } from './ornament-divider';
import { OrnateCorners } from './ornate-corners';
import { QuestLog } from './quest-log';
import { RevealText } from './reveal-text';
import { ScanSweep } from './scan-sweep';
import { StageOrbit } from './stage-orbit';
import { SummoningCircle } from './summoning-circle';
import { VictoryLayer } from './victory-layer';

describe('GeometricPattern', () => {
  it.each([8, 12, 6] as const)('draws the %i-point tiling, decorative', (kind) => {
    const { container } = render(<GeometricPattern kind={kind} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('data-pattern', String(kind));
    expect(container.querySelector('pattern')?.id).toMatch(/^tile-/);
  });

  it('defaults to the khatam', () => {
    const { container } = render(<GeometricPattern />);
    expect(container.querySelector('svg')).toHaveAttribute('data-pattern', '8');
  });
});

describe('OrnateCorners', () => {
  it('draws four decorative corners whose lines draw themselves in', () => {
    const { container } = render(<OrnateCorners />);
    const corners = container.querySelectorAll('svg.fx-corner');
    expect(corners).toHaveLength(4);
    for (const corner of corners) {
      expect(corner).toHaveAttribute('aria-hidden', 'true');
    }
    expect(container.querySelectorAll('path.fx-draw')).toHaveLength(12);
  });
});

describe('ScanSweep', () => {
  it('shows a decorative sweep with four brackets only while active', () => {
    const { container, rerender } = render(<ScanSweep active={false} />);
    expect(container.firstChild).toBeNull();
    rerender(<ScanSweep active className="extra" />);
    const sweep = container.querySelector('[data-scan="active"]');
    expect(sweep).toHaveAttribute('aria-hidden', 'true');
    expect(sweep).toHaveClass('extra');
    expect(container.querySelectorAll('.fx-bracket')).toHaveLength(4);
    expect(container.querySelector('.fx-sweep__band')).not.toBeNull();
  });
});

describe('FocusMarker', () => {
  it('is a pressable button placed by ratios, named by its object', async () => {
    const onSelect = vi.fn();
    render(
      <FocusMarker
        box={{ x: 0.1, y: 0.2, width: 0.3, height: 1.4 }}
        label="[كوب]"
        delay={0.4}
        onSelect={onSelect}
      />
    );
    const marker = screen.getByRole('button', { name: '[كوب]' });
    expect(marker).toHaveAttribute('aria-pressed', 'false');
    expect(marker.style.left).toBe('10%');
    expect(marker.style.height).toBe('100%');
    expect(marker.style.animationDelay).toBe('0.4s');
    await userEvent.click(marker);
    expect(onSelect).toHaveBeenCalledOnce();
  });

  it('marks the chosen one, dims the others, and keeps a top chip inside', () => {
    const { rerender } = render(
      <FocusMarker
        box={{ x: 0, y: 0.02, width: 0.2, height: 0.2 }}
        label="[أ]"
        selected
        onSelect={vi.fn()}
      />
    );
    const chosen = screen.getByRole('button', { pressed: true });
    expect(screen.getByText('[أ]')).toHaveClass('top-1.5');
    rerender(
      <FocusMarker
        box={{ x: 0, y: 0.5, width: 0.2, height: 0.2 }}
        label="[أ]"
        dim
        onSelect={vi.fn()}
      />
    );
    expect(chosen).toHaveClass('opacity-40');
    expect(screen.getByText('[أ]')).toHaveClass('bottom-full');
  });
});

describe('RevealText', () => {
  it('reveals words in order while screen readers get the sentence whole', () => {
    const { container } = render(
      <RevealText as="h2" text="انظر  إلى العالم" delay={0.2} className="extra" />
    );
    const heading = screen.getByRole('heading', { level: 2 });
    expect(heading).toHaveClass('extra');
    expect(heading.querySelector('.sr-only')?.textContent).toBe('انظر  إلى العالم');
    const words = Array.from(container.querySelectorAll('.fx-word')) as HTMLElement[];
    expect(words.map((word) => word.textContent)).toEqual(['انظر', 'إلى', 'العالم']);
    expect(words[2]?.style.animationDelay).toBe('0.34s');
  });

  it('is a paragraph by default', () => {
    const { container } = render(<RevealText text="سطر" />);
    expect(container.querySelector('p')).not.toBeNull();
  });
});

describe('OrnamentDivider', () => {
  it('is decorative, with an optional label read aloud', () => {
    const { container, rerender } = render(<OrnamentDivider />);
    expect(container.querySelectorAll('svg')).toHaveLength(1);
    rerender(<OrnamentDivider label="الأدلة" className="extra" />);
    expect(screen.getByText('الأدلة')).toBeInTheDocument();
    expect(container.querySelectorAll('svg')).toHaveLength(2);
    expect(container.firstElementChild).toHaveClass('extra');
  });
});

describe('Flash', () => {
  it('flash once per new trigger, never for zero', () => {
    const { container, rerender } = render(<Flash trigger={0} />);
    expect(container.firstChild).toBeNull();
    rerender(<Flash trigger={2} />);
    expect(container.querySelector('[data-flash="2"]')).not.toBeNull();
  });
});

describe('QuestLog', () => {
  it('lists every step with its state', () => {
    render(
      <QuestLog
        className="extra"
        entries={[
          { key: 'a', label: 'أ', state: 'done' },
          { key: 'b', label: 'ب', state: 'current' },
          { key: 'c', label: 'ج', state: 'pending' },
        ]}
      />
    );
    const items = screen.getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual(['أ تمّت', 'ب الآن', 'ج لاحقًا']);
    expect(items[1]).toHaveAttribute('aria-current', 'step');
    expect(screen.getByRole('list')).toHaveClass('extra');
  });
});

describe('StageOrbit', () => {
  it('turns while working and shows the seal when every stage is done', () => {
    const { container, rerender } = render(
      <StageOrbit states={['done', 'current', 'pending', 'pending']} className="extra" />
    );
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('data-orbit', 'working');
    expect(svg).toHaveClass('extra');
    expect(container.querySelectorAll('g[data-state]')).toHaveLength(4);
    expect(container.querySelector('[data-seal]')).toBeNull();
    rerender(<StageOrbit states={['done', 'done', 'done', 'done']} />);
    expect(container.querySelector('svg')).toHaveAttribute('data-orbit', 'sealed');
    expect(container.querySelector('[data-seal]')).not.toBeNull();
  });
});

describe('SummoningCircle', () => {
  it('turns slowly at rest and faster while a photo is dragged over it', () => {
    const { container, rerender } = render(<SummoningCircle />);
    const emblem = container.firstElementChild as HTMLElement;
    expect(emblem).toHaveAttribute('aria-hidden', 'true');
    expect(emblem.style.width).toBe('112px');
    expect(container.innerHTML).toContain('fx-rotate_90s');
    rerender(<SummoningCircle active size={80} />);
    expect(container.innerHTML).toContain('fx-rotate_12s');
    expect((container.firstElementChild as HTMLElement).style.width).toBe('80px');
  });
});

describe('celebrate and the victory banner', () => {
  it('bursts from the element and announces the discovery, then leaves', () => {
    vi.useFakeTimers();
    const bursts = vi.fn();
    window.addEventListener(BURST_EVENT, bursts);
    render(<VictoryLayer duration={1000} />);
    const status = screen.getByRole('status');
    expect(status).toBeEmptyDOMElement();

    const button = document.createElement('button');
    act(() => celebrate(button));
    expect(bursts).toHaveBeenCalledOnce();
    expect(status).toHaveTextContent('اكتُشِف المعنى');

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(status).toBeEmptyDOMElement();
    window.removeEventListener(BURST_EVENT, bursts);
    vi.useRealTimers();
  });

  it('uses its default duration and stops listening once gone', () => {
    const { unmount } = render(<VictoryLayer />);
    act(() => {
      window.dispatchEvent(new Event(VICTORY_EVENT));
    });
    expect(screen.getByRole('status')).toHaveTextContent('اكتُشِف المعنى');
    unmount();
    expect(() => window.dispatchEvent(new Event(VICTORY_EVENT))).not.toThrow();
  });
});
