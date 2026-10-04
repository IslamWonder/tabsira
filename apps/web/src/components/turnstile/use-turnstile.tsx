'use client';

import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { Notice } from '@/components/ui/notice';
import { loadTurnstile, TURNSTILE_WAIT_MS, turnstileHeaders } from '@/lib/turnstile';
import { messages } from '@/messages';

/** Under this width of container a phone gets the compact box instead of one that overflows. */
const FLEXIBLE_MIN_PX = 300;
/** Room kept for the box before it appears, so the form below does not jump. */
const NORMAL_HEIGHT = 'min-h-[65px]';
const COMPACT_HEIGHT = '140px';

interface Handle {
  reset: () => void;
}

interface WidgetProps {
  siteKey: string;
  handle: { current: Handle | null };
  onToken: (token: string) => void;
  onClear: () => void;
  onGiveUp: () => void;
}

/** The app's own theme when the reader chose one, else the device's. */
function themeOf(): 'light' | 'dark' | 'auto' {
  const chosen = document.documentElement.dataset.theme;
  return chosen === 'light' || chosen === 'dark' ? chosen : 'auto';
}

/**
 * The challenge itself. Cloudflare draws it in its own frame, so the app
 * controls only where it sits, the language, the theme and the room kept for
 * it. Nothing here moves on hover or animates.
 */
function Widget({ siteKey, handle, onToken, onClear, onGiveUp }: WidgetProps) {
  const container = useRef<HTMLDivElement>(null);
  // The check cannot run (an ad blocker, a network that blocks Cloudflare): the API will refuse the form, so say why.
  const [blocked, setBlocked] = useState(false);
  const giveUp = useCallback(() => {
    setBlocked(true);
    onGiveUp();
  }, [onGiveUp]);
  const take = useCallback(
    (token: string) => {
      setBlocked(false);
      onToken(token);
    },
    [onToken]
  );

  useEffect(() => {
    let cancelled = false;
    let remove: (() => void) | null = null;
    loadTurnstile().then(
      () => {
        if (cancelled) {
          return;
        }
        // Mounted and not cancelled: the container exists, and the script has defined its API.
        const box = container.current as HTMLDivElement;
        const api = window.turnstile as TurnstileApi;
        const compact = box.clientWidth < FLEXIBLE_MIN_PX;
        if (compact) {
          box.style.minHeight = COMPACT_HEIGHT;
        }
        const id = api.render(box, {
          sitekey: siteKey,
          language: 'ar',
          // No hidden input holding the token in the page: it travels in a header only.
          'response-field': false,
          theme: themeOf(),
          size: compact ? 'compact' : 'flexible',
          callback: take,
          'error-callback': giveUp,
          // A token is single-use and short-lived: drop it and fetch a fresh one.
          'expired-callback': () => {
            onClear();
            api.reset(id);
          },
        });
        remove = () => api.remove(id);
        handle.current = { reset: () => api.reset(id) };
      },
      () => {
        if (!cancelled) {
          giveUp();
        }
      }
    );
    return () => {
      cancelled = true;
      handle.current = null;
      remove?.();
    };
  }, [siteKey, handle, take, onClear, giveUp]);

  return (
    <fieldset className="m-0 min-w-0 border-0 p-0">
      <legend className="sr-only">{messages.auth.turnstile.label}</legend>
      <div ref={container} className={`w-full ${NORMAL_HEIGHT}`} />
      {blocked ? (
        <div role="alert">
          <Notice tone="error">{messages.auth.turnstile.blocked}</Notice>
        </div>
      ) : null}
    </fieldset>
  );
}

export interface UseTurnstile {
  /** Where the form shows the check: nothing at all when the site has no key. */
  widget: ReactNode;
  /**
   * The headers for the form's request. Waits (a few seconds at most) for a
   * check still running; with no key it is empty. With a check that cannot run
   * it is empty too, and the API refuses the form (it fails closed): the widget
   * has already said why.
   */
  headers: () => Promise<Record<string, string>>;
  /** Call after every submit: a token is single-use. */
  reset: () => void;
}

/** Turnstile for one form (decision 56): its widget, its header and its reset. */
export function useTurnstile(siteKey: string): UseTurnstile {
  const token = useRef<string | null>(null);
  const gaveUp = useRef(false);
  const waiters = useRef(new Set<() => void>());
  const handle = useRef<Handle | null>(null);

  const release = useCallback(() => {
    for (const wake of [...waiters.current]) {
      wake();
    }
  }, []);
  const onToken = useCallback(
    (value: string) => {
      token.current = value;
      gaveUp.current = false;
      release();
    },
    [release]
  );
  const onClear = useCallback(() => {
    token.current = null;
  }, []);
  const onGiveUp = useCallback(() => {
    token.current = null;
    gaveUp.current = true;
    release();
  }, [release]);

  const headers = useCallback(async () => {
    if (siteKey !== '' && token.current === null && !gaveUp.current) {
      await new Promise<void>((resolve) => {
        const wake = () => {
          clearTimeout(timer);
          waiters.current.delete(wake);
          resolve();
        };
        const timer = setTimeout(wake, TURNSTILE_WAIT_MS);
        waiters.current.add(wake);
      });
    }
    return turnstileHeaders(token.current);
  }, [siteKey]);

  const reset = useCallback(() => {
    token.current = null;
    handle.current?.reset();
  }, []);

  const widget =
    siteKey === '' ? null : (
      <Widget
        siteKey={siteKey}
        handle={handle}
        onToken={onToken}
        onClear={onClear}
        onGiveUp={onGiveUp}
      />
    );
  return { widget, headers, reset };
}
