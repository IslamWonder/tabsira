'use client';

import Image, { type StaticImageData } from 'next/image';
import { type ReactNode, useId, useState } from 'react';
import { cx } from '@/lib/cx';
import { useBoxSize } from '@/lib/use-box-size';
import { messages } from '@/messages';
import { InsightPoint, type PointTone } from './insight-point';
import { coverPlacement, gridCell, isRatio, labelSides } from './scene-geometry';

export interface ScenePoint {
  id: string;
  /** 0–1 ratio of the photo's width, from its left edge. */
  x: number;
  /** 0–1 ratio of the photo's height, from its top edge. */
  y: number;
  title: string;
  glimpse?: string;
  tone?: PointTone;
}

export interface ScenePhotoProps {
  src: string | StaticImageData;
  alt: string;
  /** Intrinsic size of the photo, needed to map the ratios through the crop. */
  width: number;
  height: number;
  points: readonly ScenePoint[];
  selectedId?: string;
  onSelect: (id: string) => void;
  /** The first screen's photo is the largest paint: load it first. */
  priority?: boolean;
  /** Private photos are served by the API with the visitor's session; the optimiser cannot fetch them. */
  unoptimized?: boolean;
  /** The page also shows the points as a visible list from tablet up (the scene panel). */
  listInPanel?: boolean;
  className?: string;
  /** Overlays drawn above the photo (a header, a hint). */
  children?: ReactNode;
}

/**
 * The photo as the stage (direction C): full bleed, at most three glowing
 * points (Hick's law, Choice overload), each a real button. The same points are
 * also a plain list (tajriba §10), hidden until it receives keyboard focus and
 * always read by screen readers, with each point's place in words.
 */
export function ScenePhoto({
  src,
  alt,
  width,
  height,
  points,
  selectedId,
  onSelect,
  priority = false,
  unoptimized = false,
  listInPanel = false,
  className,
  children,
}: ScenePhotoProps) {
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const size = useBoxSize(box);
  const listHeadingId = useId();
  // A point outside the photo is dropped, never guessed back into the frame.
  const valid = points.filter((point) => isRatio(point.x) && isRatio(point.y));

  const spoken = (point: ScenePoint) => {
    const { row, column } = gridCell(point);
    return messages.scene.positions[row][column];
  };

  return (
    <div ref={setBox} className={cx('relative isolate overflow-hidden', className)}>
      <Image
        src={src}
        alt={alt}
        fill
        sizes="100vw"
        priority={priority}
        unoptimized={unoptimized}
        className="object-cover"
      />
      <div aria-hidden="true" className="photo-scrim pointer-events-none absolute inset-0" />

      {valid.map((point, index) => {
        const placement = coverPlacement(point, { width, height }, size);
        if (!placement.visible) {
          return null;
        }
        const sides = labelSides(placement);
        return (
          <InsightPoint
            key={point.id}
            id={point.id}
            title={point.title}
            glimpse={point.glimpse}
            tone={point.tone}
            left={placement.left}
            top={placement.top}
            vertical={sides.vertical}
            horizontal={sides.horizontal}
            positionLabel={spoken(point)}
            selected={point.id === selectedId}
            delay={index * 1.2}
            onSelect={onSelect}
          />
        );
      })}

      {children}

      <nav
        aria-labelledby={listHeadingId}
        className={cx(
          'sr-only focus-within:not-sr-only focus-within:glass focus-within:absolute focus-within:inset-x-4 focus-within:bottom-4 focus-within:z-20 focus-within:rounded-[var(--radius-panel)] focus-within:p-4',
          // Where the panel shows the same list, this one would only repeat it.
          listInPanel && 'tablet:hidden'
        )}
      >
        <h2 id={listHeadingId} className="mb-2 font-semibold text-base text-glass-fg">
          {messages.scene.listHeading}
        </h2>
        <ul className="flex flex-col gap-1">
          {valid.map((point) => (
            <li key={point.id}>
              <button
                type="button"
                onClick={() => onSelect(point.id)}
                aria-current={point.id === selectedId ? 'true' : undefined}
                className="flex min-h-12 w-full flex-col items-start justify-center rounded-[var(--radius-card)] px-3 text-start text-glass-fg hover:bg-surface"
              >
                <span className="font-medium">{point.title}</span>{' '}
                <span className="text-[0.8125rem] text-glass-fg-soft">
                  {point.glimpse === undefined
                    ? spoken(point)
                    : messages.scene.glimpseAndPosition(point.glimpse, spoken(point))}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
