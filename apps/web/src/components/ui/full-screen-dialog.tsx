'use client';

import { type ReactNode, useRef } from 'react';
import { cx } from '@/lib/cx';
import { useModal } from './use-modal';

export interface FullScreenDialogProps {
  open: boolean;
  labelledBy: string;
  describedBy?: string;
  /** Escape leaves without a choice; omitted when a choice must be made. */
  onEscape?: () => void;
  /** Stacking: the cookie choice sits above the legal acceptance. */
  layer?: 'z-[65]' | 'z-[70]';
  children: ReactNode;
}

/**
 * A modal window over the whole screen, for the choices that come before
 * anything else: cookies, and accepting the terms. The page stays in sight
 * under a soft wash (dark at night, light by day, a hint of blur that keeps
 * it readable), and inert. It is rendered in place, not in a portal, so the
 * server can send it already open in the first paint; once the page is
 * interactive, focus starts on the window, so its title and text are read
 * first, and stays inside it. Its entrance is one fade of opacity, which
 * stops under reduced motion.
 */
export function FullScreenDialog({
  open,
  labelledBy,
  describedBy,
  onEscape,
  layer = 'z-[70]',
  children,
}: FullScreenDialogProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  useModal(open, rootRef, panelRef, { initialFocus: 'dialog', onEscape });

  if (!open) {
    return null;
  }
  return (
    <div
      ref={rootRef}
      className={cx('fx-enter fixed inset-0 overflow-y-auto overscroll-contain', layer)}
    >
      <div aria-hidden="true" className="fx-scrim pointer-events-none fixed inset-0" />
      <div className="relative flex min-h-full items-center justify-center px-4 pt-[max(40px,env(safe-area-inset-top))] pb-[max(32px,env(safe-area-inset-bottom))]">
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={labelledBy}
          aria-describedby={describedBy}
          tabIndex={-1}
          className="relative w-full max-w-[40rem] outline-none"
        >
          {children}
        </div>
      </div>
    </div>
  );
}
