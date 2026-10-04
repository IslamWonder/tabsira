'use client';

import { type RefObject, useEffect, useEffectEvent } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface ModalOptions {
  /** Escape closes the dialog; without it, Escape does nothing (a choice must be made). */
  onEscape?: () => void;
  /** Where focus lands: the first control (a visible way out), or the dialog itself, so its title and text are read first. */
  initialFocus?: 'first-control' | 'dialog';
}

/**
 * The behaviour of a modal dialog (tajriba §10): while `open`, everything in
 * <body> outside `root` is inert, the page does not scroll, focus moves into
 * `panel` and Tab cycles inside it; when it closes, all of that is undone and
 * focus returns to the control that opened it.
 */
export function useModal(
  open: boolean,
  root: RefObject<HTMLElement | null>,
  panel: RefObject<HTMLElement | null>,
  { onEscape, initialFocus = 'first-control' }: ModalOptions = {}
): void {
  const pressEscape = useEffectEvent(() => onEscape?.());
  const closesOnEscape = onEscape !== undefined;

  useEffect(() => {
    if (!open) {
      return;
    }
    // Both are mounted whenever the dialog is open: the caller renders them.
    const rootElement = root.current as HTMLElement;
    const panelElement = panel.current as HTMLElement;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // Everything at the top of <body> but the dialog, and not what holds it.
    const outside = Array.from(document.body.children).filter(
      (element) => !element.contains(rootElement) && !element.hasAttribute('inert')
    );
    for (const element of outside) {
      element.setAttribute('inert', '');
    }
    const html = document.documentElement;
    const previousOverflow = html.style.overflow;
    html.style.overflow = 'hidden';
    const first = panelElement.querySelector<HTMLElement>(FOCUSABLE);
    (initialFocus === 'dialog' || first === null ? panelElement : first).focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (closesOnEscape) {
          event.preventDefault();
          pressEscape();
        }
        return;
      }
      if (event.key !== 'Tab') {
        return;
      }
      const items = Array.from(panelElement.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const index = items.indexOf(document.activeElement as HTMLElement);
      const wraps = event.shiftKey ? index <= 0 : index === items.length - 1;
      if (wraps) {
        event.preventDefault();
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
  }, [open, root, panel, initialFocus, closesOnEscape]);
}
