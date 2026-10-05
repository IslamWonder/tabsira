'use client';

import { type ChangeEvent, type DragEvent, useState } from 'react';
import { messages } from '@/messages';
import { isImageFile } from './image-link';

export interface PhotoIntake {
  /** Hands an image to the owner, or says plainly that the file is not one. */
  take: (file: File | undefined) => void;
  /** For a file input: a cancelled picker leaves an empty list and does nothing. */
  onPick: (event: ChangeEvent<HTMLInputElement>) => void;
  /** A photo is being dragged over the drop target. */
  dragging: boolean;
  /** Spread on the element that accepts a dropped photo. */
  dropTarget: {
    onDragOver: (event: DragEvent<HTMLElement>) => void;
    onDragLeave: () => void;
    onDrop: (event: DragEvent<HTMLElement>) => void;
  };
  /** Why the last file was refused, or null. */
  error: string | null;
}

/**
 * Every way a photo comes in (Postel's law): the picker, the camera and a drop
 * all pass the same check, so a PDF is refused in the same words wherever it
 * arrives. Nothing is sent from here; the owner decides what happens with it.
 */
export function usePhotoIntake(onFile: (file: File) => void): PhotoIntake {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return {
    take,
    // A file input always has a file list; it is empty when the picker was cancelled.
    onPick: (event) => take((event.target.files as FileList)[0]),
    dragging,
    dropTarget: {
      onDragOver: (event) => {
        event.preventDefault();
        setDragging(true);
      },
      onDragLeave: () => setDragging(false),
      onDrop: (event) => {
        event.preventDefault();
        setDragging(false);
        take(event.dataTransfer.files[0]);
      },
    },
    error,
  };
}
