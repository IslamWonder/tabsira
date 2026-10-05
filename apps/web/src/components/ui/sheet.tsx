'use client';

import { type ReactNode, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { CloseIcon } from '@/components/icons';
import { messages } from '@/messages';
import { Button } from './button';
import { useModal } from './use-modal';

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  /** For previews only (the /dev/ui gallery); in the app the sheet follows <html>. */
  theme?: 'light' | 'dark';
  children: ReactNode;
}

/**
 * A modal bottom sheet (tajriba §10): focus moves into it and stays there, the
 * page behind is inert, Escape and a visible close button both close it, and
 * focus returns to the control that opened it. It rises from the thumb zone
 * (Fitts) and keeps the page in view above it, so the reader never loses the
 * screen they came from (Working memory).
 */
export function Sheet({ open, onClose, title, description, theme, children }: SheetProps) {
  const titleId = useId();
  const descriptionId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  useModal(open, rootRef, panelRef, { onEscape: onClose });

  if (!open || typeof document === 'undefined') {
    return null;
  }

  return createPortal(
    <div
      ref={rootRef}
      data-theme={theme}
      className="fixed inset-0 z-50 flex items-end justify-center bg-transparent"
    >
      {/* A pointer shortcut only, hidden from assistive technology: Escape and the close button are the keyboard paths. */}
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-[rgba(4,10,8,0.55)] motion-safe:animate-fade-in"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description === undefined ? undefined : descriptionId}
        tabIndex={-1}
        // As tall as the screen allows below the status bar: a fixed share of it pushed a
        // live camera's controls out of sight on a small phone. The header never scrolls.
        className="glass relative flex max-h-[calc(100dvh-env(safe-area-inset-top)-16px)] w-full max-w-xl flex-col rounded-t-[28px] border-b-0 shadow-[var(--panel-shadow)] motion-safe:animate-rise"
      >
        <span aria-hidden="true" className="mx-auto mt-2.5 h-1.5 w-11 rounded-full bg-line" />
        <header className="flex shrink-0 items-start justify-between gap-3 px-5 pt-2">
          <div className="flex flex-col gap-1 pt-2">
            <h2 id={titleId} className="font-semibold text-fg text-subheading">
              {title}
            </h2>
            {description === undefined ? null : (
              <p id={descriptionId} className="text-fg-soft text-sm">
                {description}
              </p>
            )}
          </div>
          <Button
            variant="icon"
            label={messages.sheet.close}
            onClick={onClose}
            className="shrink-0"
          >
            <CloseIcon />
          </Button>
        </header>
        <div className="min-h-0 overflow-y-auto overscroll-contain px-5 pt-3 pb-[max(24px,env(safe-area-inset-bottom))]">
          {children}
        </div>
      </div>
    </div>,
    document.body
  );
}
