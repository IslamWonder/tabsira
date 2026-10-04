import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { setAmbientMotion } from '@/preferences/motion';
import { manualFrames } from '@/test/fake-canvas';
import { CountUp } from './count-up';
import { FocusCursor } from './focus-cursor';

function cursor() {
  return document.querySelector('.fx-cursor') as HTMLElement;
}

describe('FocusCursor', () => {
  it('follows keyboard focus to the start side of the focused item', () => {
    render(
      <>
        <FocusCursor />
        <button type="button">أول</button>
      </>
    );
    const button = screen.getByRole('button');
    vi.spyOn(button, 'matches').mockReturnValue(true);
    vi.spyOn(button, 'getBoundingClientRect').mockReturnValue(new DOMRect(100, 50, 80, 40));
    act(() => button.focus());
    expect(cursor().dataset.visible).toBe('true');
    expect(cursor().style.transform).toBe('translate(186px, 62px)');
    act(() => button.blur());
    expect(cursor().dataset.visible).toBe('false');
  });

  it('ignores mouse focus, follows touch focus, and keeps inside the screen', () => {
    render(
      <>
        <FocusCursor />
        <button type="button">أول</button>
      </>
    );
    const button = screen.getByRole('button');
    vi.spyOn(button, 'matches').mockImplementation(() => {
      throw new Error('unsupported selector');
    });
    vi.spyOn(button, 'getBoundingClientRect').mockReturnValue(new DOMRect(900, 50, 200, 40));
    act(() => button.focus());
    expect(cursor().dataset.visible).toBe('false');
    act(() => button.blur());

    act(() => {
      window.dispatchEvent(new PointerEvent('pointerdown', { pointerType: 'touch' }));
    });
    act(() => button.focus());
    expect(cursor().dataset.visible).toBe('true');
    expect(cursor().style.transform).toBe(`translate(${window.innerWidth - 20}px, 62px)`);

    act(() => {
      window.dispatchEvent(new Event('scroll'));
      window.dispatchEvent(new Event('resize'));
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab' }));
    });
    Object.defineProperty(button, 'isConnected', { get: () => false, configurable: true });
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(cursor().dataset.visible).toBe('false');
  });

  it('stops listening once removed', () => {
    const { unmount } = render(<FocusCursor />);
    unmount();
    expect(() => window.dispatchEvent(new Event('resize'))).not.toThrow();
  });
});

describe('CountUp', () => {
  it('renders the true value first, in Arabic digits, then rolls up to it', () => {
    const frames = manualFrames();
    render(<CountUp value={30} duration={1} className="extra" />);
    const number = screen.getByText(/[٠-٩]/);
    expect(number).toHaveClass('extra');
    act(() => frames.step(500));
    expect(number.textContent).not.toBe('٣٠');
    act(() => frames.step(600));
    expect(number.textContent).toBe('٣٠');
    expect(frames.pending).toBe(false);
  });

  it('shows the value at once when decorative motion is off', () => {
    setAmbientMotion(false);
    const frames = manualFrames();
    render(<CountUp value={7} />);
    expect(screen.getByText('٧')).toBeInTheDocument();
    expect(frames.pending).toBe(false);
  });

  it('stops rolling when removed', () => {
    const frames = manualFrames();
    const { unmount } = render(<CountUp value={5} />);
    unmount();
    expect(frames.pending).toBe(false);
  });
});
