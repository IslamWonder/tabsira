'use client';

import {
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';
import { MinusIcon, PlusIcon, RecenterIcon } from '@/components/icons';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { motionAllowed } from '@/preferences/motion';
import type { Reveal } from '@/world/api';
import { LandmarkIcon } from './landmark-icons';
import {
  circleAt,
  drawFog,
  easeOut,
  type FogCircle,
  LANDMARK_DELAY_MS,
  REVEAL_DURATION_MS,
  REVEAL_STAGGER_MS,
} from './world-fog';
import {
  type Camera,
  canvasSize,
  centerOf,
  centerOn,
  clampCamera,
  MAX_ZOOM,
  MIN_ZOOM,
  PAN_STEP,
  type Point,
  panBy,
  type Size,
  stageSize,
  zoomAround,
  zoomStep,
} from './world-geometry';
import { type Landmark, THEME_COLORS } from './world-model';
import { CLOUDS_SRC, LANDSCAPE_SRC, loadPicture } from './world-pictures';

const M = messages.world;
/** A flight the reader asked for (go to an insight's spot, the reset): short, eased out. */
const FLIGHT_MS = 520;
// One notch of a mouse wheel zooms by about a sixth.
const WHEEL_ZOOM = 0.0015;

/**
 * Where the camera looks: a point of the picture, once per new `key`; `fly` eases there.
 * `shift` moves where it lands, in screen pixels, out from under a panel left open; `minZoom`
 * zooms in that far first, since at zoom 1 the picture may have no room to move aside.
 */
export interface Focus {
  point: Point;
  key: number;
  fly: boolean;
  shift?: Point;
  minZoom?: number;
}

export interface WorldStageProps {
  /** Every reveal of the owner, the ones still to play among them. */
  reveals: readonly Reveal[];
  landmarks: readonly Landmark[];
  /** Reveals whose effect has not played: they stay under the clouds until it does. */
  pending: readonly Reveal[];
  /** The pending reveals have played (or were shown at once, under reduced motion). */
  onPlayed: (ids: readonly string[]) => void;
  focus: Focus;
  /** Where the reset button and Home go back to. */
  home: Point;
  label: (landmark: Landmark) => string;
  onOpen: (landmark: Landmark) => void;
}

type Pictures = { status: 'loading' } | { status: 'ready'; clouds: HTMLImageElement | null };

/** The circles to cut now: shown reveals whole, playing ones as far as their effect has come. */
function circlesFor(
  reveals: readonly Reveal[],
  waiting: ReadonlySet<string>,
  playing: readonly Reveal[],
  elapsed: number
): FogCircle[] {
  return reveals.flatMap((reveal) => {
    const circle = { x: reveal.x, y: reveal.y, radius: reveal.radius };
    const index = playing.findIndex((item) => item.id === reveal.id);
    if (index >= 0) {
      const own = elapsed - index * REVEAL_STAGGER_MS;
      return own > 0 ? [circleAt(circle, reveal.theme, own)] : [];
    }
    return waiting.has(reveal.id) ? [] : [{ ...circle, amount: 1 }];
  });
}

function pointIn(element: HTMLElement, event: { clientX: number; clientY: number }): Point {
  const box = element.getBoundingClientRect();
  return { x: event.clientX - box.left, y: event.clientY - box.top };
}

/** The pointers held down, and what they do: one moves the picture, two pinch it. */
interface Gesture {
  pointers: Map<number, Point>;
  last: Point | null;
  distance: number | null;
}

function middle(points: readonly Point[]): Point {
  const [a, b] = points as [Point, Point];
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function spread(points: readonly Point[]): number {
  const [a, b] = points as [Point, Point];
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/**
 * The world picture (decision 59): the ground under a canvas of opaque clouds,
 * with the landmarks of what was learned, moved by dragging, pinching, the
 * wheel, the keyboard (arrows, + and −, Home) and the three buttons. Until the
 * clouds are drawn the ground stays hidden behind the same cloud picture, so
 * no frame ever shows the world uncovered; nothing is drawn again while
 * nothing changes. New reveals play once: the clouds part over 1.4 s, eased
 * out, and the landmark arrives as they start to part; under reduced motion
 * they are simply there.
 */
export function WorldStage({
  reveals,
  landmarks,
  pending,
  onPlayed,
  focus,
  home,
  label,
  onOpen,
}: Readonly<WorldStageProps>) {
  const helpId = useId();
  const viewportRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const camera = useRef<Camera>({ x: 0, y: 0, zoom: MIN_ZOOM });
  const view = useRef<Size>({ width: 0, height: 0 });
  const flight = useRef<number | null>(null);
  const focused = useRef<number | null>(null);
  const gesture = useRef<Gesture>({ pointers: new Map(), last: null, distance: null });
  const [stage, setStage] = useState<Size | null>(null);
  const [limits, setLimits] = useState({ atMin: true, atMax: false });
  const [pictures, setPictures] = useState<Pictures>({ status: 'loading' });
  const [drawn, setDrawn] = useState(false);
  const [playing, setPlaying] = useState<readonly Reveal[]>([]);
  // Played here already: never again, even before the owner of `pending` hears of it.
  const [done, setDone] = useState<ReadonlySet<string>>(() => new Set());
  const waiting = new Set(
    pending.filter((reveal) => !done.has(reveal.id)).map((reveal) => reveal.id)
  );

  const apply = useCallback((next: Camera) => {
    camera.current = next;
    const element = stageRef.current as HTMLDivElement;
    element.style.transform = `translate3d(${next.x}px, ${next.y}px, 0) scale(${next.zoom})`;
    element.style.setProperty('--world-zoom', String(next.zoom));
    const atMin = next.zoom <= MIN_ZOOM;
    const atMax = next.zoom >= MAX_ZOOM;
    setLimits((current) =>
      current.atMin === atMin && current.atMax === atMax ? current : { atMin, atMax }
    );
  }, []);

  const stopFlight = useCallback(() => {
    if (flight.current !== null) {
      cancelAnimationFrame(flight.current);
      flight.current = null;
    }
  }, []);

  const moveTo = useCallback(
    (target: Camera, fly: boolean) => {
      stopFlight();
      if (!fly || !motionAllowed()) {
        apply(target);
        return;
      }
      const from = camera.current;
      const start = performance.now();
      const step = (now: number) => {
        const t = easeOut((now - start) / FLIGHT_MS);
        apply({
          x: from.x + (target.x - from.x) * t,
          y: from.y + (target.y - from.y) * t,
          zoom: from.zoom + (target.zoom - from.zoom) * t,
        });
        flight.current = t < 1 ? requestAnimationFrame(step) : null;
      };
      flight.current = requestAnimationFrame(step);
    },
    [apply, stopFlight]
  );

  // The viewport's size: measured now and on every change, keeping the middle of the view in place.
  useEffect(() => {
    const element = viewportRef.current as HTMLElement;
    const measure = () => {
      const next = { width: element.clientWidth, height: element.clientHeight };
      const before = view.current;
      if (next.width === before.width && next.height === before.height) {
        return;
      }
      const kept = before.width > 0 ? centerOf(camera.current, before) : null;
      view.current = next;
      setStage(stageSize(next));
      if (kept !== null) {
        apply(centerOn(next, kept, camera.current.zoom));
      }
    };
    measure();
    if (typeof ResizeObserver === 'undefined') {
      return;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [apply]);

  useEffect(() => {
    if (stage === null || focused.current === focus.key) {
      return;
    }
    focused.current = focus.key;
    const zoom = Math.max(camera.current.zoom, focus.minZoom ?? MIN_ZOOM);
    const centred = centerOn(view.current, focus.point, zoom);
    const shift = focus.shift ?? { x: 0, y: 0 };
    moveTo(
      clampCamera({ ...centred, x: centred.x + shift.x, y: centred.y + shift.y }, view.current),
      focus.fly
    );
  }, [focus, stage, moveTo]);

  useEffect(() => stopFlight, [stopFlight]);

  useEffect(() => {
    let live = true;
    void loadPicture(CLOUDS_SRC).then((clouds) => {
      if (live) {
        setPictures({ status: 'ready', clouds });
      }
    });
    return () => {
      live = false;
    };
  }, []);

  const paint = useCallback(
    (elapsed: number): boolean => {
      const canvas = canvasRef.current as HTMLCanvasElement;
      if (pictures.status === 'loading' || stage === null) {
        return false;
      }
      const context = canvas.getContext('2d');
      if (context === null) {
        return false;
      }
      const size = canvasSize(stage, window.devicePixelRatio || 1);
      if (canvas.width !== size.width || canvas.height !== size.height) {
        canvas.width = size.width;
        canvas.height = size.height;
      }
      const hidden = new Set(
        pending.filter((reveal) => !done.has(reveal.id)).map((reveal) => reveal.id)
      );
      drawFog(context, size, pictures.clouds, circlesFor(reveals, hidden, playing, elapsed));
      return true;
    },
    [pictures, stage, reveals, pending, playing, done]
  );

  const finish = useCallback(
    (ids: readonly string[]) => {
      setDone((current) => new Set([...current, ...ids]));
      onPlayed(ids);
    },
    [onPlayed]
  );

  // Drawn again only when something changed; while an effect plays, its own frames draw.
  useEffect(() => {
    if (playing.length === 0 && paint(0)) {
      setDrawn(true);
    }
  }, [paint, playing.length]);

  useEffect(() => {
    const next = pending.filter((reveal) => !done.has(reveal.id));
    if (!drawn || next.length === 0 || playing.length > 0) {
      return;
    }
    if (motionAllowed()) {
      setPlaying(next);
    } else {
      finish(next.map((reveal) => reveal.id));
    }
  }, [drawn, pending, done, playing.length, finish]);

  useEffect(() => {
    if (playing.length === 0) {
      return;
    }
    const start = performance.now();
    const total = REVEAL_DURATION_MS + (playing.length - 1) * REVEAL_STAGGER_MS;
    let frame = requestAnimationFrame(function step(now: number) {
      const elapsed = now - start;
      paint(elapsed);
      if (elapsed < total) {
        frame = requestAnimationFrame(step);
        return;
      }
      setPlaying([]);
      finish(playing.map((reveal) => reveal.id));
    });
    return () => cancelAnimationFrame(frame);
  }, [playing, paint, finish]);

  // The wheel zooms about the pointer; it must be able to stop the page's own scrolling.
  useEffect(() => {
    const element = viewportRef.current as HTMLElement;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      stopFlight();
      const zoom = camera.current.zoom * Math.exp(-event.deltaY * WHEEL_ZOOM);
      apply(zoomAround(camera.current, view.current, zoom, pointIn(element, event)));
    };
    element.addEventListener('wheel', onWheel, { passive: false });
    return () => element.removeEventListener('wheel', onWheel);
  }, [apply, stopFlight]);

  /** Start again from the pointers still down, so lifting one finger of a pinch never jumps. */
  const restart = () => {
    const points = [...gesture.current.pointers.values()];
    gesture.current.last = points.length === 1 ? (points[0] as Point) : null;
    gesture.current.distance = points.length >= 2 ? spread(points) : null;
    if (points.length >= 2) {
      gesture.current.last = middle(points);
    }
  };

  const onPointerDown = (event: PointerEvent<HTMLElement>) => {
    if ((event.target as Element).closest('[data-landmark]') !== null) {
      return;
    }
    if (event.pointerType === 'mouse' && event.button !== 0) {
      return;
    }
    stopFlight();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    gesture.current.pointers.set(event.pointerId, pointIn(event.currentTarget, event));
    restart();
  };

  const onPointerMove = (event: PointerEvent<HTMLElement>) => {
    const { pointers } = gesture.current;
    if (!pointers.has(event.pointerId)) {
      return;
    }
    pointers.set(event.pointerId, pointIn(event.currentTarget, event));
    const points = [...pointers.values()];
    const last = gesture.current.last as Point;
    if (points.length === 1) {
      const point = points[0] as Point;
      apply(panBy(camera.current, view.current, point.x - last.x, point.y - last.y));
      gesture.current.last = point;
      return;
    }
    const center = middle(points);
    const distance = spread(points);
    const before = gesture.current.distance as number;
    const zoomed = zoomAround(
      camera.current,
      view.current,
      camera.current.zoom * (before > 0 ? distance / before : 1),
      center
    );
    apply(panBy(zoomed, view.current, center.x - last.x, center.y - last.y));
    gesture.current.last = center;
    gesture.current.distance = distance;
  };

  const onPointerEnd = (event: PointerEvent<HTMLElement>) => {
    if (gesture.current.pointers.delete(event.pointerId)) {
      restart();
    }
  };

  const zoomBy = (direction: 1 | -1) => {
    stopFlight();
    apply(zoomStep(camera.current, view.current, direction));
  };

  const recenter = () => moveTo(centerOn(view.current, home, MIN_ZOOM), true);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [PAN_STEP, 0],
      ArrowRight: [-PAN_STEP, 0],
      ArrowUp: [0, PAN_STEP],
      ArrowDown: [0, -PAN_STEP],
    };
    const move = moves[event.key];
    if (move !== undefined) {
      stopFlight();
      apply(panBy(camera.current, view.current, move[0], move[1]));
    } else if (event.key === '+' || event.key === '=') {
      zoomBy(1);
    } else if (event.key === '-' || event.key === '_') {
      zoomBy(-1);
    } else if (event.key === 'Home') {
      recenter();
    } else {
      return;
    }
    event.preventDefault();
  };

  const width = stage?.width ?? 0;
  const height = stage?.height ?? 0;

  return (
    <>
      <section
        ref={viewportRef}
        aria-label={M.mapLabel}
        aria-describedby={helpId}
        // biome-ignore lint/a11y/noNoninteractiveTabindex: the picture moves with the arrow keys, so it takes focus.
        tabIndex={0}
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerEnd}
        onPointerCancel={onPointerEnd}
        onLostPointerCapture={onPointerEnd}
        className="world-clouds absolute inset-0 cursor-grab touch-none select-none overflow-hidden outline-none focus-visible:outline-3 focus-visible:outline-[var(--focus)] focus-visible:outline-offset-[-6px] active:cursor-grabbing"
      >
        <p id={helpId} className="sr-only">
          {M.mapHelp}
        </p>
        <div
          ref={stageRef}
          className="world-stage"
          style={{ width, height, visibility: drawn ? 'visible' : 'hidden' }}
        >
          {/* biome-ignore lint/performance/noImgElement: one decorative picture of this site, drawn under a canvas and transformed with it. */}
          <img
            src={LANDSCAPE_SRC}
            alt=""
            draggable={false}
            decoding="async"
            className="absolute inset-0 block size-full"
          />
          <canvas ref={canvasRef} className="absolute inset-0 block size-full" />
          {playing.map((reveal, index) => (
            <span
              key={`accent-${reveal.id}`}
              aria-hidden="true"
              data-accent={reveal.theme}
              className={`world-accent world-accent--${reveal.theme}`}
              style={
                {
                  left: reveal.x * width,
                  top: reveal.y * height,
                  '--accent': THEME_COLORS[reveal.theme],
                  '--accent-size': `${reveal.radius * width * 2}px`,
                  animationDelay: `${index * REVEAL_STAGGER_MS}ms`,
                } as CSSProperties
              }
            />
          ))}
          {drawn
            ? landmarks.map((landmark) => {
                const { reveal } = landmark;
                const arriving = playing.findIndex((item) => item.id === reveal.id);
                if (arriving < 0 && waiting.has(reveal.id)) {
                  return null;
                }
                return (
                  <button
                    key={reveal.id}
                    type="button"
                    data-landmark={reveal.id}
                    aria-label={label(landmark)}
                    onClick={() => onOpen(landmark)}
                    className={cx(
                      'world-landmark group flex flex-col items-center gap-1.5 outline-none',
                      arriving >= 0 && 'world-landmark--arriving'
                    )}
                    style={{
                      left: reveal.x * width,
                      top: reveal.y * height,
                      animationDelay:
                        arriving >= 0
                          ? `${arriving * REVEAL_STAGGER_MS + LANDMARK_DELAY_MS}ms`
                          : undefined,
                    }}
                  >
                    <span
                      className="world-marker flex size-12 items-center justify-center rounded-full border-2 group-focus-visible:outline-3 group-focus-visible:outline-[var(--focus)] group-focus-visible:outline-offset-2"
                      style={{
                        color: THEME_COLORS[reveal.theme],
                        borderColor: THEME_COLORS[reveal.theme],
                      }}
                    >
                      <LandmarkIcon icon={reveal.icon} />
                    </span>
                    <span aria-hidden="true" className="world-name">
                      {landmark.name}
                    </span>
                  </button>
                );
              })
            : null}
        </div>
      </section>
      <fieldset
        aria-label={M.controls}
        className="world-pearl absolute m-0 min-w-0 p-0 bottom-[calc(var(--nav-clearance)-8px)] left-3 z-10 flex flex-col overflow-hidden rounded-[18px] tablet:bottom-7 tablet:left-7 [@media(max-height:480px)]:flex-row"
      >
        <button
          type="button"
          aria-label={M.zoomIn}
          onClick={() => zoomBy(1)}
          disabled={limits.atMax}
          className="world-control"
        >
          <PlusIcon />
        </button>
        <button
          type="button"
          aria-label={M.zoomOut}
          onClick={() => zoomBy(-1)}
          disabled={limits.atMin}
          className="world-control"
        >
          <MinusIcon />
        </button>
        <button type="button" aria-label={M.recenter} onClick={recenter} className="world-control">
          <RecenterIcon />
        </button>
      </fieldset>
    </>
  );
}
