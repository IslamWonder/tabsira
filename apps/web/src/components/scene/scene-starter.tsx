'use client';

import { type ChangeEvent, type DragEvent, type FormEvent, useId, useState } from 'react';
import { SummoningCircle } from '@/components/fx/summoning-circle';
import { CameraIcon } from '@/components/icons';
import { Button, buttonClasses } from '@/components/ui/button';
import { cx } from '@/lib/cx';
import { ar } from '@/messages/ar';
import { isImageFile, normaliseImageLink } from './image-link';

export interface SceneStarterProps {
  onFile: (file: File) => void;
  onLink: (url: string) => void;
  className?: string;
}

/**
 * Every way into a new scene (Postel's law: accept each input form): drop a
 * photo, choose a file, paste a link, or use the camera on a phone. Dropping
 * always has a button equivalent, and nothing is sent from here: the page that
 * owns the analysis decides what happens with the file or the link.
 */
export function SceneStarter({ onFile, onLink, className }: SceneStarterProps) {
  const [dragging, setDragging] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileId = useId();
  const cameraId = useId();
  const linkId = useId();
  const errorId = useId();

  const take = (file: File | undefined) => {
    if (file === undefined) {
      return;
    }
    if (isImageFile(file)) {
      setError(null);
      onFile(file);
    } else {
      setError(ar.scene.starter.notImage);
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

  const onSubmitLink = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const field = event.currentTarget.elements.namedItem('link') as HTMLInputElement;
    const url = normaliseImageLink(field.value);
    if (url === null) {
      setError(ar.scene.starter.invalidLink);
      return;
    }
    setError(null);
    onLink(url);
  };

  return (
    <section
      aria-label={ar.scene.starter.prompt}
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
        <p className="m-0 font-heading font-semibold text-fg text-lg leading-snug">
          {dragging ? ar.scene.starter.dropping : ar.scene.starter.prompt}
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
          {ar.scene.starter.choose}
          <input id={fileId} type="file" accept="image/*" className="sr-only" onChange={onPick} />
        </label>
        {/* Phones open the camera straight away; larger screens rarely have one facing the scene. */}
        <label
          htmlFor={cameraId}
          className={cx(
            buttonClasses('secondary'),
            'cursor-pointer tablet:hidden has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-[var(--focus)] has-[:focus-visible]:outline-offset-2'
          )}
        >
          <CameraIcon width="18" height="18" />
          {ar.scene.starter.camera}
          <input
            id={cameraId}
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            onChange={onPick}
          />
        </label>
        <Button
          variant="ghost"
          aria-expanded={linkOpen}
          aria-controls={linkId}
          onClick={() => setLinkOpen((open) => !open)}
          className="border border-line"
        >
          {ar.scene.starter.pasteLink}
        </Button>
      </div>

      <form
        id={linkId}
        hidden={!linkOpen}
        onSubmit={onSubmitLink}
        className="flex flex-wrap items-end gap-2.5"
        noValidate
      >
        <label className="flex min-w-0 flex-1 flex-col gap-1 text-fg-soft text-sm">
          {ar.scene.starter.linkLabel}
          <input
            name="link"
            type="url"
            inputMode="url"
            dir="ltr"
            autoComplete="off"
            aria-describedby={error === null ? undefined : errorId}
            aria-invalid={error === ar.scene.starter.invalidLink}
            className="min-h-12 rounded-[var(--radius-card)] border border-line bg-surface px-3 text-base text-fg"
          />
        </label>
        <Button type="submit" variant="secondary">
          {ar.scene.starter.useLink}
        </Button>
      </form>

      <p id={errorId} role="alert" className="m-0 text-danger text-sm empty:hidden">
        {error}
      </p>
    </section>
  );
}
