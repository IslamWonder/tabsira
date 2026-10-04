/**
 * Cloudflare Turnstile on the five forms that bots abuse (decision 56). The
 * script comes from Cloudflare only on a page that renders one of them and only
 * when the web server has a site key; never from the root layout.
 */

export const TURNSTILE_SCRIPT =
  'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

/** The header the API reads the token from; never the JSON body. */
export const TURNSTILE_HEADER = 'CF-Turnstile-Response';

/** How long a submit waits for a check still running before it goes without a token. */
export const TURNSTILE_WAIT_MS = 8000;

let pending: Promise<void> | null = null;

/**
 * Loads the script at most once per page, however many widgets mount. A failed
 * load is forgotten, so a later mount may try again.
 */
export function loadTurnstile(): Promise<void> {
  if (window.turnstile !== undefined) {
    return Promise.resolve();
  }
  if (pending === null) {
    pending = new Promise<void>((resolve, reject) => {
      const script = document.createElement('script');
      script.src = TURNSTILE_SCRIPT;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('turnstile script failed to load'));
      document.head.appendChild(script);
    }).catch((error: unknown) => {
      pending = null;
      throw error;
    });
  }
  return pending;
}

/** The request headers for a token: the one header, or none (key unset, check unreachable). */
export function turnstileHeaders(token: string | null): Record<string, string> {
  return token === null ? {} : { [TURNSTILE_HEADER]: token };
}
