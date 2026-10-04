'use client';

import { type ReactNode, useEffect, useEffectEvent, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { CloseIcon } from '@/components/icons';
import { ar } from '@/messages/ar';
import { Button } from './button';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

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
  const close = useEffectEvent(() => onClose());

  useEffect(() => {
    if (!open) {
      return;
    }
    // Both are mounted whenever the sheet is open: the portal renders them.
    const root = rootRef.current as HTMLDivElement;
    const panel = panelRef.current as HTMLDivElement;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const outside = Array.from(document.body.children).filter(
      (element) => element !== root && !element.hasAttribute('inert')
    );
    for (const element of outside) {
      element.setAttribute('inert', '');
    }
    const html = document.documentElement;
    const previousOverflow = html.style.overflow;
    html.style.overflow = 'hidden';
    // The close button comes first, so focus lands on a visible way out.
    (panel.querySelector(FOCUSABLE) as HTMLElement).focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== 'Tab') {
        return;
      }
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      const index = items.indexOf(document.activeElement as HTMLElement);
      const wraps = event.shiftKey ? index <= 0 : index === items.length - 1;
      if (wraps) {
        event.preventDefault();
        // The close button is always inside, so the list is never empty.
        (items[event.shiftKey ? items.length - 1 : 0] as HTMLElement).focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      for (const element of outside) {
        element.removeAttribute('inert');
      }
      html.style.overflow = previousOverflow;
      opener?.focus();
    };
  }, [open]);

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
        className="glass relative flex max-h-[88dvh] w-full max-w-xl flex-col rounded-t-[28px] border-b-0 shadow-[var(--panel-shadow)] motion-safe:animate-rise"
      >
        <span aria-hidden="true" className="mx-auto mt-2.5 h-1.5 w-11 rounded-full bg-line" />
        <header className="flex items-start justify-between gap-3 px-5 pt-2">
          <div className="flex flex-col gap-1 pt-2">
            <h2 id={titleId} className="font-bold text-fg text-xl">
              {title}
            </h2>
            {description === undefined ? null : (
              <p id={descriptionId} className="text-fg-soft text-sm">
                {description}
              </p>
            )}
          </div>
          <Button variant="icon" label={ar.sheet.close} onClick={onClose} className="shrink-0">
            <CloseIcon />
          </Button>
        </header>
        <div className="overflow-y-auto overscroll-contain px-5 pt-3 pb-[max(24px,env(safe-area-inset-bottom))]">
          {children}
        </div>
      </div>
    </div>,
    document.body
  );
}
