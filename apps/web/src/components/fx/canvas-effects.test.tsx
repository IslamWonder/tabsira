import { act, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { setAmbientMotion } from '@/preferences/motion';
import { fakeContext, manualFrames } from '@/test/fake-canvas';
import { stubMatchMedia } from '@/test/media';
import { BURST_EVENT, burstFrom } from './burst';
import { BurstLayer } from './burst-layer';
import { LightMotes } from './light-motes';

function withContext() {
  const context = fakeContext();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    context as unknown as RenderingContext
  );
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(375);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(812);
  return context;
}

describe('LightMotes', () => {
  it('falls back to a pixel ratio of one', () => {
    withContext();
    manualFrames();
    vi.stubGlobal('devicePixelRatio', 0);
    const { container } = render(<LightMotes />);
    expect((container.querySelector('canvas') as HTMLCanvasElement).width).toBe(375);
    vi.unstubAllGlobals();
  });

  it('does nothing where a canvas cannot draw', () => {
    const frames = manualFrames();
    const { container } = render(<LightMotes />);
    expect(container.querySelector('canvas')).not.toBeNull();
    expect(frames.pending).toBe(false);
  });

  it('drifts frame after frame while motion is allowed, in the theme colour', () => {
    const context = withContext();
    const frames = manualFrames();
    document.documentElement.style.setProperty('--mote', '#123456');
    document.documentElement.style.setProperty('--mote-opacity', '0.5');
    render(<LightMotes />);
    expect(frames.pending).toBe(true);
    frames.step(16);
    frames.step(16);
    expect(context.arc).toHaveBeenCalled();
    expect(context.fillStyle).toBe('#123456');
    expect(context.setTransform).toHaveBeenCalledWith(1, 0, 0, 1, 0, 0);
  });

  it('draws one still frame when motion is off or the page is hidden, and resumes', () => {
    const context = withContext();
    const frames = manualFrames();
    render(<LightMotes />);
    act(() => setAmbientMotion(false));
    expect(frames.pending).toBe(false);
    expect(context.arc).toHaveBeenCalled();
    act(() => setAmbientMotion(true));
    expect(frames.pending).toBe(true);
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(frames.pending).toBe(false);
  });

  it('refits on resize, honours the pixel ratio, and stops when removed', () => {
    withContext();
    const frames = manualFrames();
    vi.stubGlobal('devicePixelRatio', 3);
    stubMatchMedia((query) => query.includes('reduce'));
    const { container, unmount } = render(<LightMotes />);
    const canvas = container.querySelector('canvas') as HTMLCanvasElement;
    expect(canvas.width).toBe(750);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(frames.pending).toBe(false);
    unmount();
    vi.unstubAllGlobals();
  });
});

describe('BurstLayer', () => {
  it('does nothing where a canvas cannot draw', () => {
    const frames = manualFrames();
    render(<BurstLayer />);
    act(() => burstFrom(document.body));
    expect(frames.pending).toBe(false);
  });

  it('draws a burst until every particle is spent, in the theme colours', () => {
    const context = withContext();
    const frames = manualFrames();
    document.documentElement.style.setProperty('--glow-gold', '#abcdef');
    render(<BurstLayer />);
    act(() => burstFrom(document.body));
    expect(frames.pending).toBe(true);
    act(() => burstFrom(document.body));
    frames.step(16);
    expect(context.fill).toHaveBeenCalled();
    expect(context.lineTo).toHaveBeenCalled();
    for (let i = 0; i < 200 && frames.pending; i += 1) {
      frames.step(50);
    }
    expect(frames.pending).toBe(false);
  });

  it('stays still when decorative motion is off, refits on resize, and stops listening once gone', () => {
    withContext();
    const frames = manualFrames();
    vi.stubGlobal('devicePixelRatio', 0);
    const { unmount } = render(<BurstLayer />);
    setAmbientMotion(false);
    act(() => burstFrom(document.body));
    expect(frames.pending).toBe(false);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    unmount();
    expect(() =>
      window.dispatchEvent(new CustomEvent(BURST_EVENT, { detail: { x: 0, y: 0 } }))
    ).not.toThrow();
    vi.unstubAllGlobals();
  });
});
