/**
 * The subset of Cloudflare Turnstile's global API this app uses. No types
 * package exists for it and a script loaded from Cloudflare's own address is
 * not worth a dependency; src/lib/turnstile.ts and the widget in
 * src/components/turnstile/ are the only code that touches `window.turnstile`.
 */
interface TurnstileRenderOptions {
  sitekey: string;
  callback?: (token: string) => void;
  'error-callback'?: () => void;
  'expired-callback'?: () => void;
  language?: string;
  'response-field'?: boolean;
  theme?: 'light' | 'dark' | 'auto';
  size?: 'normal' | 'flexible' | 'compact';
}

interface TurnstileApi {
  render: (container: HTMLElement, options: TurnstileRenderOptions) => string;
  reset: (widgetId?: string) => void;
  remove: (widgetId: string) => void;
}

interface Window {
  turnstile?: TurnstileApi;
}
