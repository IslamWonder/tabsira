'use client';

import { useEffect, useRef } from 'react';
import { KHATAM_RATIO, starPoints } from './geometry';

const SIZE = 16;
const GAP = 6;

/** Whether the browser itself would show a focus ring here (keyboard, not a mouse click). */
function keyboardFocus(element: Element): boolean {
  try {
    return element.matches(':focus-visible');
  } catch {
    return false;
  }
}

/**
 * The selection cursor of an RPG menu: a small luminous eight-point star that
 * glides to the item that has focus, beside it on the start side. It follows
 * keyboard and touch focus only, never the mouse and never hover
 * (DESIGN_DECISION.md «Game feel»); the focus ring stays, the star adds to it.
 * Decorative, outside the accessibility tree, and it jumps instead of gliding
 * when motion is reduced.
 */
export function FocusCursor() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cursor = ref.current as HTMLDivElement;
    let target: Element | null = null;
    let touch = false;

    const place = () => {
      if (target === null || !target.isConnected) {
        cursor.dataset.visible = 'false';
        return;
      }
      const box = target.getBoundingClientRect();
      // Arabic reads from the right: the star sits just outside the start edge.
      const x = Math.min(window.innerWidth - SIZE - 4, box.right + GAP);
      const y = box.top + box.height / 2 - SIZE / 2;
      cursor.style.transform = `translate(${x}px, ${y}px)`;
      cursor.dataset.visible = 'true';
    };

    const onFocusIn = (event: FocusEvent) => {
      const element = event.target as Element;
      target = touch || keyboardFocus(element) ? element : null;
      place();
    };
    const onFocusOut = () => {
      target = null;
      place();
    };
    const onPointerDown = (event: PointerEvent) => {
      touch = event.pointerType === 'touch';
    };
    const onKeyDown = () => {
      touch = false;
    };

    window.addEventListener('focusin', onFocusIn);
    window.addEventListener('focusout', onFocusOut);
    window.addEventListener('pointerdown', onPointerDown, true);
    window.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    return () => {
      window.removeEventListener('focusin', onFocusIn);
      window.removeEventListener('focusout', onFocusOut);
      window.removeEventListener('pointerdown', onPointerDown, true);
      window.removeEventListener('keydown', onKeyDown, true);
      window.removeEventListener('scroll', place, true);
      window.removeEventListener('resize', place);
    };
  }, []);

  return (
    <div ref={ref} aria-hidden="true" data-visible="false" className="fx-cursor">
      <svg viewBox="0 0 24 24" className="fx-cursor__star" aria-hidden="true" focusable="false">
        <polygon points={starPoints(12, 12, 11, 11 * KHATAM_RATIO)} fill="currentColor" />
        <circle cx="12" cy="12" r="2.6" style={{ fill: 'var(--glow-gold)' }} />
      </svg>
    </div>
  );
}
