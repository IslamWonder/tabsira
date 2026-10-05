'use client';

import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { CameraCapture } from './camera-capture';
import { usePhotoIntake } from './use-photo-intake';

export interface SceneStarterProps {
  onFile: (file: File) => void;
  /** Start the live camera at once: the sheet holding the starter was opened by the reader's tap. */
  startCamera?: boolean;
  className?: string;
}

/**
 * The capture sheet's content, camera first (decision 51: no link): the live
 * camera with its shutter, the gallery beside it, and on a screen with a
 * mouse a dropped photo too (Postel's law). Nothing is sent from here: the
 * page that owns the analysis decides what happens with the file.
 */
export function SceneStarter({ onFile, startCamera = false, className }: SceneStarterProps) {
  const intake = usePhotoIntake(onFile);
  return (
    <section
      aria-label={messages.scene.capture.heading}
      {...intake.dropTarget}
      className={cx(
        'flex flex-col gap-4 rounded-[24px] outline-2 outline-transparent outline-dashed outline-offset-4 transition-[outline-color] duration-200',
        intake.dragging && 'outline-[var(--focus)]',
        className
      )}
    >
      <CameraCapture onFile={intake.take} onPick={intake.onPick} autoStart={startCamera} />

      <p className="m-0 hidden text-center text-fg-muted text-sm pointer-fine:block">
        {intake.dragging ? messages.scene.starter.dropping : messages.scene.capture.drop}
      </p>

      <p className="m-0 text-[0.8125rem] text-fg-muted leading-[1.8]">{messages.sending.privacy}</p>

      <p role="alert" className="m-0 text-danger text-sm empty:hidden">
        {intake.error}
      </p>
    </section>
  );
}
