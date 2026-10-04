'use client';

import { type ChangeEvent, type DragEvent, useId, useState } from 'react';
import { SummoningCircle } from '@/components/fx/summoning-circle';
import { buttonClasses } from '@/components/ui/button';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { CameraCapture } from './camera-capture';
import { isImageFile } from './image-link';

export interface SceneStarterProps {
  onFile: (file: File) => void;
  className?: string;
}

/**
 * Every way into a new scene (Postel's law: accept each input form): drop a
 * photo, choose a file, or take a photo with the camera (decision 51: no link). Dropping
 * always has a button equivalent, and nothing is sent from here: the page that
 * owns the analysis decides what happens with the file.
 */
export function SceneStarter({ onFile, className }: SceneStarterProps) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileId = useId();
  const errorId = useId();

  const take = (file: File | undefined) => {
    if (file === undefined) {
      return;
    }
    if (isImageFile(file)) {
      setError(null);
      onFile(file);
    } else {
      setError(messages.scene.starter.notImage);
    }
  };

  // A file input always has a file list; it is empty when the picker was cancelled.
  const onPick = (event: ChangeEvent<HTMLInputElement>) =>
    take((event.target.files as FileList)[0]);

  const onDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    setDragging(false);
    take(event.dataTransfer.files[0]);
  };

  return (
    <section
      aria-label={messages.scene.starter.prompt}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cx(
        'flex flex-col gap-4 rounded-[24px] border-[1.5px] border-dashed p-5 transition-colors duration-200',
        dragging
          ? 'border-[var(--focus)] bg-[var(--chip-primary-bg)]'
          : 'border-[var(--dropzone-border)] bg-surface',
        className
      )}
    >
      <div className="flex flex-col items-center gap-3 text-center desktop:flex-row desktop:gap-4 desktop:text-start">
        <SummoningCircle active={dragging} size={96} />
        <p className="m-0 font-semibold text-fg text-lg leading-snug">
          {dragging ? messages.scene.starter.dropping : messages.scene.starter.prompt}
        </p>
      </div>

      <div className="flex flex-wrap gap-2.5">
        <label
          htmlFor={fileId}
          className={cx(
            buttonClasses('secondary'),
            'cursor-pointer has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-[var(--focus)] has-[:focus-visible]:outline-offset-2'
          )}
        >
          {messages.scene.starter.choose}
          <input id={fileId} type="file" accept="image/*" className="sr-only" onChange={onPick} />
        </label>
        {/* A live camera in the page, as the earlier prototype had; the phone's camera app otherwise. */}
        <CameraCapture onFile={take} onPick={onPick} />
      </div>

      <p className="m-0 text-fg-muted text-sm leading-[1.8]">{messages.sending.privacy}</p>

      <p id={errorId} role="alert" className="m-0 text-danger text-sm empty:hidden">
        {error}
      </p>
    </section>
  );
}
