'use client';

import { type ReactNode, useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { CloseIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { useModal } from '@/components/ui/use-modal';
import { messages } from '@/messages';

export interface WorldPanelProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  /** A drawing beside the title: the landmark's, for a place. */
  icon?: ReactNode;
  children: ReactNode;
}

/**
 * What the world opens on request (decision 59): a panel at the side of the
 * picture from tablet up, 440 px wide, and a bottom sheet on a phone. It is a
 * modal dialog (tajriba §10): titled and described, focus kept inside, Escape
 * and the close button both close it, and focus returns to what opened it. Its
 * body scrolls on its own, so the close button never leaves the screen. When
 * what it shows changes (a place opened from «بصائري»), focus moves to the new
 * title, so nothing focused is ever removed under the reader.
 */
export function WorldPanel({ open, onClose, title, description, icon, children }: WorldPanelProps) {
  const titleId = useId();
  const descriptionId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const shown = useRef<string | null>(null);
  useModal(open, rootRef, panelRef, { onEscape: onClose });

  useEffect(() => {
    if (!open) {
      shown.current = null;
      return;
    }
    if (shown.current !== null && shown.current !== title) {
      headingRef.current?.focus();
    }
    shown.current = title;
  }, [open, title]);

  if (!open || typeof document === 'undefined') {
    return null;
  }

  return createPortal(
    <div ref={rootRef} className="fixed inset-0 z-50">
      {/* A pointer shortcut only: Escape and the close button are the keyboard paths. */}
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-[rgba(4,10,8,0.45)] motion-safe:animate-fade-in tablet:bg-[rgba(4,10,8,0.2)]"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        className="absolute inset-x-0 bottom-0 flex max-h-[calc(100dvh-env(safe-area-inset-top)-24px)] flex-col rounded-t-[28px] border border-line border-b-0 bg-canvas text-fg shadow-[var(--panel-shadow)] outline-none motion-safe:animate-rise tablet:inset-x-auto tablet:start-6 tablet:top-[calc(var(--topbar-height)+16px)] tablet:bottom-6 tablet:max-h-none tablet:w-[440px] tablet:rounded-[24px] tablet:border-b desktop:w-[460px]"
      >
        <span
          aria-hidden="true"
          className="mx-auto mt-2.5 h-1.5 w-11 shrink-0 rounded-full bg-line tablet:hidden"
        />
        <header className="flex shrink-0 items-start justify-between gap-3 px-5 pt-3 pb-2 tablet:px-6 tablet:pt-5">
          <div className="flex min-w-0 items-start gap-3">
            {icon === undefined ? null : (
              <span className="world-marker mt-0.5 flex size-11 shrink-0 items-center justify-center rounded-full border-2">
                {icon}
              </span>
            )}
            <div className="flex min-w-0 flex-col gap-0.5">
              <h2
                id={titleId}
                ref={headingRef}
                tabIndex={-1}
                className="m-0 font-bold font-display text-[1.5rem] text-fg leading-[1.4] outline-none"
              >
                {title}
              </h2>
              <p id={descriptionId} className="m-0 text-[0.9375rem] text-fg-soft leading-[1.8]">
                {description}
              </p>
            </div>
          </div>
          <Button
            variant="icon"
            label={messages.world.panel.close}
            onClick={onClose}
            className="shrink-0"
          >
            <CloseIcon />
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pt-2 pb-[max(24px,env(safe-area-inset-bottom))] tablet:px-6">
          {children}
        </div>
      </div>
    </div>,
    document.body
  );
}
