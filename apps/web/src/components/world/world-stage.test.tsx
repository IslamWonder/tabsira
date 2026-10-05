import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setAmbientMotion } from '@/preferences/motion';
import { manualFrames } from '@/test/fake-canvas';
import { REVEALS, WORLD, WORLD_JUST_LEARNED } from '@/test/world';
import type { Reveal } from '@/world/api';
import { REVEAL_DURATION_MS } from './world-fog';
import { landmarks } from './world-model';
import { type Focus, WorldStage, type WorldStageProps } from './world-stage';

const pictures = vi.hoisted(() => ({ clouds: {} as HTMLImageElement | null }));
vi.mock('./world-pictures', () => ({
  LANDSCAPE_SRC: '/world/landscape-1.webp',
  CLOUDS_SRC: '/world/clouds-1.webp',
  loadPicture: () => Promise.resolve(pictures.clouds),
}));

function fakeContext() {
  const gradient = { addColorStop: vi.fn() };
  return {
    globalCompositeOperation: 'source-over',
    fillStyle: '' as unknown,
    clearRect: vi.fn(),
    drawImage: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    createRadialGradient: vi.fn(() => gradient),
    createLinearGradient: vi.fn(() => gradient),
  };
}

let size = { width: 390, height: 700 };
let context: ReturnType<typeof fakeContext> | null;

beforeEach(() => {
  pictures.clouds = {} as HTMLImageElement;
  size = { width: 390, height: 700 };
  context = fakeContext();
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => size.width);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(() => size.height);
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    left: 0,
    top: 0,
  } as DOMRect);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    () => context as unknown as RenderingContext
  );
});

afterEach(() => {
  setAmbientMotion(true);
});

const focus = (point = { x: 0.5, y: 0.5 }, key = 0, fly = false): Focus => ({ point, key, fly });

function stage(props: Partial<WorldStageProps> = {}) {
  const onOpen = vi.fn();
  const onPlayed = vi.fn();
  const view = render(
    <WorldStage
      reveals={WORLD.reveals}
      landmarks={landmarks(WORLD)}
      pending={[]}
      onPlayed={onPlayed}
      focus={focus()}
      home={{ x: 0.5, y: 0.5 }}
      label={(landmark) => `افتح ${landmark.name}`}
      onOpen={onOpen}
      {...props}
    />
  );
  const viewport = screen.getByRole('region', { name: /عالمك/ });
  const picture = viewport.querySelector('.world-stage') as HTMLElement;
  return { ...view, onOpen, onPlayed, viewport, picture };
}

function translation(picture: HTMLElement): [number, number, number] {
  const match = /translate3d\((-?[\d.]+)px, (-?[\d.]+)px, 0\) scale\(([\d.]+)\)/.exec(
    picture.style.transform
  );
  return match === null
    ? [Number.NaN, 0, 0]
    : [Number(match[1]), Number(match[2]), Number(match[3])];
}

describe('WorldStage', () => {
  it('keeps the ground hidden until the clouds are drawn, then shows the landmarks', async () => {
    const { picture, onOpen } = stage();

    expect(picture.style.visibility).toBe('hidden');
    expect(screen.queryByRole('button', { name: /افتح/ })).toBeNull();
    const button = await screen.findByRole('button', { name: 'افتح [موضع أول]' });

    expect(picture.style.visibility).toBe('visible');
    expect(screen.getAllByRole('button', { name: /افتح/ })).toHaveLength(2);
    expect(context?.drawImage).toHaveBeenCalled();
    // Three reveals cut, none still to play.
    expect(context?.arc).toHaveBeenCalledTimes(3);
    await userEvent.click(button);
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ name: '[موضع أول]' }));
  });

  it('never shows the ground where the canvas cannot draw', async () => {
    context = null;
    const { picture } = stage();
    await act(async () => undefined);
    expect(picture.style.visibility).toBe('hidden');
    expect(screen.queryByRole('button', { name: /افتح/ })).toBeNull();
  });

  it('draws opaque clouds of its own when the cloud picture fails', async () => {
    pictures.clouds = null;
    stage();
    await screen.findByRole('button', { name: 'افتح [موضع أول]' });
    expect(context?.drawImage).not.toHaveBeenCalled();
    expect(context?.fillRect).toHaveBeenCalled();
  });

  it('moves with the arrows, zooms with + and −, and goes home with Home', async () => {
    const { viewport, picture } = stage();
    await screen.findByRole('button', { name: 'افتح [موضع أول]' });
    const [x] = translation(picture);
    const zoomIn = screen.getByRole('button', { name: 'كبّر' });
    const zoomOut = screen.getByRole('button', { name: 'صغّر' });
    expect(zoomOut).toBeDisabled();

    fireEvent.keyDown(viewport, { key: 'ArrowLeft' });
    expect(translation(picture)[0]).toBe(x + 64);
    fireEvent.keyDown(viewport, { key: 'ArrowRight' });
    fireEvent.keyDown(viewport, { key: 'ArrowRight' });
    expect(translation(picture)[0]).toBe(x - 64);
    fireEvent.keyDown(viewport, { key: 'ArrowUp' });
    fireEvent.keyDown(viewport, { key: 'ArrowDown' });
    fireEvent.keyDown(viewport, { key: '+' });
    expect(translation(picture)[2]).toBe(1.25);
    expect(zoomOut).toBeEnabled();
    for (let press = 0; press < 4; press += 1) {
      fireEvent.keyDown(viewport, { key: '=' });
    }
    expect(translation(picture)[2]).toBe(2);
    expect(zoomIn).toBeDisabled();
    fireEvent.keyDown(viewport, { key: '-' });
    fireEvent.keyDown(viewport, { key: '_' });
    expect(translation(picture)[2]).toBe(1.5);
    await userEvent.click(zoomOut);
    await userEvent.click(zoomIn);
    expect(translation(picture)[2]).toBe(1.5);

    setAmbientMotion(false);
    fireEvent.keyDown(viewport, { key: 'Home' });
    expect(translation(picture)).toEqual([195 - 525, 0, 1]);
    // Other keys are left to the page.
    expect(fireEvent.keyDown(viewport, { key: 'a' })).toBe(true);
  });

  it('flies home when motion is allowed, and stops when the reader takes over', async () => {
    const frames = manualFrames();
    const { viewport, picture } = stage();
    await screen.findByRole('button', { name: 'افتح [موضع أول]' });
    fireEvent.keyDown(viewport, { key: 'ArrowLeft' });

    await userEvent.click(screen.getByRole('button', { name: 'أعد العالم إلى موضعه' }));
    act(() => frames.step(100));
    act(() => frames.step(1000));
    expect(translation(picture)).toEqual([195 - 525, 0, 1]);
    expect(frames.pending).toBe(false);

    await userEvent.click(screen.getByRole('button', { name: 'أعد العالم إلى موضعه' }));
    fireEvent.keyDown(viewport, { key: '+' });
    expect(frames.pending).toBe(false);
  });

  it('pans with one pointer, pinches with two, and never jumps when a finger lifts', async () => {
    const { viewport, picture } = stage();
    await screen.findByRole('button', { name: 'افتح [موضع أول]' });
    const [x] = translation(picture);

    fireEvent.pointerDown(viewport, { pointerId: 1, clientX: 200, clientY: 300, button: 0 });
    fireEvent.pointerMove(viewport, { pointerId: 1, clientX: 150, clientY: 300 });
    expect(translation(picture)[0]).toBe(x - 50);
    fireEvent.pointerDown(viewport, { pointerId: 2, clientX: 250, clientY: 300 });
    fireEvent.pointerMove(viewport, { pointerId: 2, clientX: 350, clientY: 300 });
    expect(translation(picture)[2]).toBeGreaterThan(1);
    fireEvent.pointerUp(viewport, { pointerId: 2 });
    const [afterPinch] = translation(picture);
    fireEvent.pointerMove(viewport, { pointerId: 1, clientX: 150, clientY: 300 });
    expect(translation(picture)[0]).toBe(afterPinch);
    fireEvent.pointerCancel(viewport, { pointerId: 1 });
    fireEvent.pointerMove(viewport, { pointerId: 1, clientX: 0, clientY: 0 });
    expect(translation(picture)[0]).toBe(afterPinch);
    fireEvent.pointerUp(viewport, { pointerId: 9 });

    // Another mouse button, or a press on a landmark, moves nothing.
    fireEvent.pointerDown(viewport, {
      pointerId: 3,
      pointerType: 'mouse',
      clientX: 10,
      clientY: 10,
      button: 2,
    });
    fireEvent.pointerMove(viewport, { pointerId: 3, clientX: 90, clientY: 10 });
    const landmark = screen.getByRole('button', { name: 'افتح [موضع أول]' });
    fireEvent.pointerDown(landmark, { pointerId: 4, clientX: 10, clientY: 10, button: 0 });
    fireEvent.pointerMove(viewport, { pointerId: 4, clientX: 90, clientY: 10 });
    expect(translation(picture)[0]).toBe(afterPinch);
  });

  it('zooms about the pointer with the wheel', async () => {
    const { viewport, picture } = stage();
    await screen.findByRole('button', { name: 'افتح [موضع أول]' });

    fireEvent.wheel(viewport, { deltaY: -400, clientX: 195, clientY: 350 });

    expect(translation(picture)[2]).toBeGreaterThan(1.5);
  });

  it('keeps the middle of the view in place when the screen turns', async () => {
    let resized: () => void = () => undefined;
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: () => void) {
          resized = callback;
        }
        observe() {}
        disconnect() {}
      }
    );
    const { picture } = stage({ focus: focus({ x: 0.3, y: 0.5 }) });
    await screen.findByRole('button', { name: 'افتح [موضع أول]' });

    size = { width: 390, height: 700 };
    act(() => resized());
    size = { width: 844, height: 390 };
    act(() => resized());

    const [x, , zoom] = translation(picture);
    expect(zoom).toBe(1);
    // The picture is now 844 wide: the point 0.3 stays as near the middle as the edge allows.
    expect(x).toBe(0);
  });

  it('plays a new reveal once: clouds part, the landmark arrives, then it is shown', async () => {
    const frames = manualFrames();
    const pending = WORLD_JUST_LEARNED.reveals;
    const { onPlayed, container, rerender } = stage({
      reveals: pending,
      landmarks: landmarks(WORLD_JUST_LEARNED),
      pending,
    });
    await act(async () => undefined);

    const landmark = screen.getByRole('button', { name: 'افتح [موضع أول]' });
    expect(landmark).toHaveClass('world-landmark--arriving');
    expect(container.querySelector('[data-accent="knowledge"]')).not.toBeNull();
    context?.arc.mockClear();
    act(() => frames.step(REVEAL_DURATION_MS / 2));
    expect(context?.arc).toHaveBeenCalledOnce();
    expect(onPlayed).not.toHaveBeenCalled();
    act(() => frames.step(REVEAL_DURATION_MS));

    expect(onPlayed).toHaveBeenCalledExactlyOnceWith(['6001']);
    expect(container.querySelector('[data-accent]')).toBeNull();
    expect(screen.getByRole('button', { name: 'افتح [موضع أول]' })).not.toHaveClass(
      'world-landmark--arriving'
    );
    // Its owner has not marked it shown yet: it does not play again.
    rerender(
      <WorldStage
        reveals={pending}
        landmarks={landmarks(WORLD_JUST_LEARNED)}
        pending={[...pending]}
        onPlayed={onPlayed}
        focus={focus()}
        home={{ x: 0.5, y: 0.5 }}
        label={(item) => `افتح ${item.name}`}
        onOpen={vi.fn()}
      />
    );
    expect(frames.pending).toBe(false);
    expect(onPlayed).toHaveBeenCalledOnce();
  });

  it('shows a new reveal at once under reduced motion', async () => {
    setAmbientMotion(false);
    const later = { ...(REVEALS[1] as Reveal), shown: false };
    const reveals = [REVEALS[0] as Reveal, later];
    const { onPlayed, container } = stage({
      reveals,
      landmarks: landmarks({ ...WORLD, reveals }),
      pending: [later],
    });
    await screen.findByRole('button', { name: 'افتح [موضع ثان]' });

    expect(onPlayed).toHaveBeenCalledExactlyOnceWith(['6002']);
    expect(container.querySelector('[data-accent]')).toBeNull();
    expect(screen.getByRole('button', { name: 'افتح [موضع ثان]' })).not.toHaveClass(
      'world-landmark--arriving'
    );
  });

  it('flies to a new focus once per key', async () => {
    const frames = manualFrames();
    const { rerender, picture, onPlayed } = stage();
    await screen.findByRole('button', { name: 'افتح [موضع أول]' });
    const props = {
      reveals: WORLD.reveals,
      landmarks: landmarks(WORLD),
      pending: [],
      onPlayed,
      home: { x: 0.5, y: 0.5 },
      label: () => 'x',
      onOpen: vi.fn(),
    };

    rerender(<WorldStage {...props} focus={focus({ x: 0, y: 0 }, 1, true)} />);
    act(() => frames.step(2000));
    expect(translation(picture)).toEqual([0, 0, 1]);
    rerender(<WorldStage {...props} focus={focus({ x: 1, y: 1 }, 1, true)} />);
    expect(frames.pending).toBe(false);
  });
});

describe('WorldStage, the edges', () => {
  it('plays several new reveals one after the other', async () => {
    const frames = manualFrames();
    const both = WORLD.reveals.slice(0, 2).map((reveal) => ({ ...reveal, shown: false }));
    const { onPlayed } = stage({
      reveals: both,
      landmarks: landmarks({ ...WORLD, reveals: both }),
      pending: both,
    });
    await act(async () => undefined);
    context?.arc.mockClear();

    act(() => frames.step(100));
    // The second has not started yet: one circle only.
    expect(context?.arc).toHaveBeenCalledOnce();
    act(() => frames.step(3000));
    expect(onPlayed).toHaveBeenCalledExactlyOnceWith(['6001', '6002']);
  });

  it('stops loading its clouds when it leaves first', () => {
    const { unmount } = stage();
    unmount();
    expect(screen.queryByRole('region')).toBeNull();
  });

  it('draws at density 1 where the screen gives none, and pinches two fingers that start together', async () => {
    vi.stubGlobal('devicePixelRatio', 0);
    const { viewport, picture } = stage();
    await screen.findByRole('button', { name: 'افتح [موضع أول]' });

    fireEvent.pointerDown(viewport, { pointerId: 1, clientX: 100, clientY: 100, button: 0 });
    fireEvent.pointerDown(viewport, { pointerId: 2, clientX: 100, clientY: 100, button: 0 });
    fireEvent.pointerMove(viewport, { pointerId: 2, clientX: 160, clientY: 100 });

    expect(translation(picture)[2]).toBe(1);
  });
});
