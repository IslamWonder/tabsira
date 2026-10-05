'use client';

import { useId } from 'react';
import { CameraIcon, GalleryIcon } from '@/components/icons';
import { Button, buttonClasses } from '@/components/ui/button';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { PhotoPicker } from './photo-picker';
import { usePhotoIntake } from './use-photo-intake';

const T = messages.scene.capture;

export interface CaptureCardProps {
  /** Opens the capture sheet, its live camera starting on this tap. */
  onCamera: () => void;
  /** A photo chosen or dropped here. */
  onFile: (file: File) => void;
  className?: string;
}

/**
 * The invitation to a scene of one's own, the core of the product: one glowing
 * call to take a photo (Von Restorff, Fitts: the widest target in the thumb
 * zone), the gallery beside it as the second way (Hick: two choices, no more),
 * and on a screen with a mouse the card also takes a dropped photo. The
 * privacy line is said here, before anything leaves the device.
 */
export function CaptureCard({ onCamera, onFile, className }: CaptureCardProps) {
  const headingId = useId();
  const intake = usePhotoIntake(onFile);
  return (
    <section
      aria-labelledby={headingId}
      {...intake.dropTarget}
      className={cx(
        'glass flex flex-col gap-4 rounded-[var(--radius-panel)] p-5 shadow-[var(--panel-shadow)] transition-colors duration-200',
        intake.dragging && 'border-[var(--focus)] bg-[var(--chip-primary-bg)]',
        className
      )}
    >
      <div className="flex flex-col gap-1">
        <h2 id={headingId} className="m-0 font-semibold text-fg text-subheading">
          {T.heading}
        </h2>
        <p className="m-0 text-[0.9375rem] text-fg-soft leading-relaxed">{T.lead}</p>
      </div>

      <div className="grid grid-cols-[3fr_2fr] gap-2.5">
        <Button
          variant="cta"
          onClick={onCamera}
          aria-haspopup="dialog"
          className="whitespace-nowrap px-4"
        >
          <CameraIcon width="20" height="20" />
          {T.camera}
        </Button>
        <PhotoPicker
          onPick={intake.onPick}
          className={buttonClasses('secondary', 'md', 'whitespace-nowrap px-3')}
        >
          <GalleryIcon width="20" height="20" />
          {messages.scene.starter.choose}
        </PhotoPicker>
      </div>

      {/* Only a pointer that can drag reads this; on a phone it would promise what cannot happen. */}
      <p className="m-0 hidden text-center text-fg-muted text-sm pointer-fine:block">
        {intake.dragging ? messages.scene.starter.dropping : T.drop}
      </p>

      <p className="m-0 text-[0.8125rem] text-fg-muted leading-[1.8]">{messages.sending.privacy}</p>

      <p role="alert" className="m-0 text-danger text-sm empty:hidden">
        {intake.error}
      </p>
    </section>
  );
}
