'use client';

import Image from 'next/image';
import { useId, useState } from 'react';
import { FocusMarker } from '@/components/fx/focus-marker';
import { containFrame } from '@/components/insight/scene-geometry';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { cx } from '@/lib/cx';
import type { ScanEntity } from '@/lib/scan/api';
import { useBoxSize } from '@/lib/use-box-size';
import { messages } from '@/messages';

const T = messages.scan.focus;

export interface FocusStageProps {
  src: string;
  width: number;
  height: number;
  alt: string;
  entities: readonly ScanEntity[];
  selectedId: string | undefined;
  onSelect: (id: string) => void;
}

/**
 * The whole photo, uncropped, with a bracketed box over each thing the scene
 * found (tajriba S08): the reader points at what caught their eye. The boxes
 * are the server's 0–1 ratios laid over the photo exactly as it is drawn, and
 * each is a real button, pressed when chosen. A thing with no box is only in
 * the list beside the photo.
 */
export function FocusStage({
  src,
  width,
  height,
  alt,
  entities,
  selectedId,
  onSelect,
}: FocusStageProps) {
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const size = useBoxSize(box);
  const frame = containFrame({ width, height }, size);
  return (
    <div ref={setBox} className="relative h-full w-full">
      <Image src={src} alt={alt} fill unoptimized sizes="100vw" className="object-contain" />
      <fieldset
        className="absolute m-0 min-w-0 border-0 p-0"
        style={{
          left: `${frame.left}%`,
          top: `${frame.top}%`,
          width: `${frame.width}%`,
          height: `${frame.height}%`,
        }}
      >
        <legend className="sr-only">{T.photoLabel}</legend>
        {entities.map((entity, index) =>
          entity.bbox === null ? null : (
            <FocusMarker
              key={entity.id}
              box={entity.bbox}
              label={entity.label_arabic}
              selected={entity.id === selectedId}
              dim={selectedId !== undefined}
              delay={index * 0.12}
              onSelect={() => onSelect(entity.id)}
            />
          )
        )}
      </fieldset>
    </div>
  );
}

export interface FocusPanelProps {
  entities: readonly ScanEntity[];
  selectedId: string | undefined;
  onSelect: (id: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
  acting: boolean;
  error: string | null;
}

/**
 * The same choice as a list (tajriba §10): every thing the scene found, as
 * buttons that stay pressed, with one clear action to look at the chosen one
 * and a way back that costs nothing (Hick's law: one decision, one question).
 * A thing the scene only inferred says so, so what is seen and what is
 * supposed are never blurred (tajriba §3.8).
 */
export function FocusPanel({
  entities,
  selectedId,
  onSelect,
  onConfirm,
  onCancel,
  acting,
  error,
}: FocusPanelProps) {
  const headingId = useId();
  const chosen = entities.find((entity) => entity.id === selectedId);
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <h2 id={headingId} className="m-0 font-semibold text-subheading text-fg">
          {T.title}
        </h2>
        <p className="m-0 text-fg-soft leading-[1.8]">{T.hint}</p>
      </div>

      {entities.length === 0 ? (
        <p className="m-0 text-fg-soft leading-[1.8]">{T.none}</p>
      ) : (
        <ul aria-label={T.listLabel} className="m-0 flex list-none flex-wrap gap-2.5 p-0">
          {entities.map((entity) => (
            <li key={entity.id}>
              <button
                type="button"
                aria-pressed={entity.id === selectedId}
                onClick={() => onSelect(entity.id)}
                className={cx(
                  'inline-flex min-h-12 items-center gap-2 rounded-full border px-4 text-[1rem] text-fg transition-colors duration-200',
                  entity.id === selectedId
                    ? 'border-[var(--glow-gold)] bg-[var(--chip-primary-bg)] font-semibold'
                    : 'border-line bg-surface'
                )}
              >
                {entity.label_arabic}
                {entity.status === 'inferred' ? (
                  <span className="text-[0.8125rem] text-fg-muted">{T.inferred}</span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      )}

      <p role="status" className="m-0 min-h-6 font-medium text-fg-soft text-sm">
        {chosen === undefined ? null : T.chosen(chosen.label_arabic)}
      </p>
      {error === null ? null : (
        <div role="alert">
          <Notice tone="error">{error}</Notice>
        </div>
      )}

      <div className="flex flex-wrap gap-2.5">
        <Button onClick={onConfirm} disabled={chosen === undefined || acting} aria-busy={acting}>
          {acting ? T.confirming : T.confirm}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={acting}>
          {T.cancel}
        </Button>
      </div>
    </section>
  );
}
